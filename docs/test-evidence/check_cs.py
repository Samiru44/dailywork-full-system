"""
Static sanity checks on the C# sources. This is NOT a compiler — the .NET SDK
is unavailable in this environment — but it catches the structural mistakes that
hand-written C# is prone to: unbalanced delimiters, missing usings for types
that are referenced, DTO properties used by controllers but never declared,
and services injected but never registered.
"""
import pathlib, re, sys

ROOT = pathlib.Path(sys.argv[1])
fails = []

def check(label, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + label + (("  -> " + detail) if detail else ""))
    if not ok:
        fails.append(label)

def strip(src):
    """Remove strings, chars and comments so delimiter counting is meaningful."""
    s = re.sub(r'"""[\s\S]*?"""', '""', src)          # raw string literals
    s = re.sub(r'@"(?:[^"]|"")*"', '""', s)           # verbatim strings
    s = re.sub(r'\$?"(?:[^"\\\n]|\\.)*"', '""', s)    # normal / interpolated
    s = re.sub(r"'(?:[^'\\]|\\.)'", "''", s)          # char literals
    s = re.sub(r'//[^\n]*', '', s)
    s = re.sub(r'/\*[\s\S]*?\*/', '', s)
    return s

files = sorted(ROOT.rglob("*.cs"))
print(f"checking {len(files)} C# files\n")

# ---------------------------------------------------------------
# 1. Delimiter balance
# ---------------------------------------------------------------
bad = []
for f in files:
    s = strip(f.read_text())
    for a, b in [("{", "}"), ("(", ")"), ("[", "]")]:
        if s.count(a) != s.count(b):
            bad.append(f"{f.name} {a}{b} {s.count(a)}/{s.count(b)}")
check("all files have balanced delimiters", not bad, "; ".join(bad))

# ---------------------------------------------------------------
# 2. Namespaces resolve
# ---------------------------------------------------------------
declared, needed = set(), set()
for f in files:
    t = f.read_text()
    m = re.search(r'^namespace\s+([\w.]+)\s*;', t, re.M)
    if m:
        declared.add(m.group(1))
    needed |= set(re.findall(r'^using\s+(DailyWork[\w.]*)\s*;', t, re.M))
check("every DailyWork using resolves", not (needed - declared), str(needed - declared))

# ---------------------------------------------------------------
# 3. DTO properties referenced by controllers actually exist
# ---------------------------------------------------------------
dto_src = (ROOT / "Dtos" / "Dtos.cs").read_text()
dto_classes = {}
for m in re.finditer(r'public class (\w+)\s*\{([\s\S]*?)\n\}', dto_src):
    name, body = m.group(1), m.group(2)
    props = set(re.findall(r'public\s+[\w<>?\[\],\s]+?\s(\w+)\s*\{\s*get;', body))
    dto_classes[name] = props

missing_props = []
for f in files:
    if "Controllers" not in str(f) and "Services" not in str(f):
        continue
    text = strip(f.read_text())
    for cls, props in dto_classes.items():
        # find "new ClassName { A = ..., B = ... }" initialisers
        for init in re.finditer(r'new\s+' + cls + r'\s*\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}', text):
            body = init.group(1)

            # Strip nested initialisers such as
            #     Jobs = rows.Select(j => new ProjectJobDto { Title = ... })
            # so their properties are attributed to that type and not to this
            # one. Each nested type is checked by its own pass over the file.
            while True:
                stripped = re.sub(r'new\s+\w+\s*\{[^{}]*\}', '', body)
                if stripped == body:
                    break
                body = stripped

            # a real assignment: '=' not part of '==', '!=', '<=', '>=', '=>'
            for prop in re.findall(r'(\w+)\s*(?<![=!<>])=(?![=>])', body):
                if prop and prop[0].isupper() and prop not in props:
                    missing_props.append(f"{f.name}: {cls}.{prop}")

check("no controller sets a DTO property that does not exist",
      not missing_props, "; ".join(sorted(set(missing_props))[:6]))

# ---------------------------------------------------------------
# 4. Injected services are registered in Program.cs
# ---------------------------------------------------------------
program = (ROOT / "Program.cs").read_text()
service_names = {f.stem for f in (ROOT / "Services").glob("*.cs")}
injected = set()
for f in files:
    if "Controllers" not in str(f):
        continue
    for m in re.finditer(r'public\s+\w+Controller\s*\(([^)]*)\)', f.read_text()):
        for param in m.group(1).split(","):
            parts = param.strip().split()
            if len(parts) >= 2 and parts[0] in service_names:
                injected.add(parts[0])

unregistered = [s for s in injected if f"<{s}>" not in program]
check("every injected service is registered", not unregistered, str(unregistered))

# ---------------------------------------------------------------
# 5. Models referenced by the DbContext exist
# ---------------------------------------------------------------
ctx = (ROOT / "Data" / "AppDbContext.cs").read_text()
model_names = {f.stem for f in (ROOT / "Models").glob("*.cs")}
entities = set(re.findall(r'DbSet<(\w+)>', ctx))
check("every DbSet maps to a model file", entities <= model_names, str(entities - model_names))

# ---------------------------------------------------------------
# 6. Entity properties configured in the DbContext exist on the model
# ---------------------------------------------------------------
bad_cfg = []
for m in re.finditer(r'mb\.Entity<(\w+)>\(\)\s*\.Property\(\w+\s*=>\s*\w+\.(\w+)\)', ctx):
    entity, prop = m.group(1), m.group(2)
    path = ROOT / "Models" / f"{entity}.cs"
    if path.exists() and not re.search(r'\b' + prop + r'\b\s*\{\s*get;', path.read_text()):
        bad_cfg.append(f"{entity}.{prop}")
check("configured properties exist on their models", not bad_cfg, str(bad_cfg))

# ---------------------------------------------------------------
# 7. Controllers declare a route and the class name matches the file
# ---------------------------------------------------------------
route_issues = []
for f in (ROOT / "Controllers").glob("*.cs"):
    t = f.read_text()
    if '[Route(' not in t:
        route_issues.append(f"{f.name}: no [Route]")
    if f'class {f.stem}' not in t:
        route_issues.append(f"{f.name}: class name mismatch")
check("controllers are well formed", not route_issues, str(route_issues))

# ---------------------------------------------------------------
# 8. No secret left in appsettings
# ---------------------------------------------------------------
settings = (ROOT / "appsettings.json").read_text()
key = re.search(r'"Key"\s*:\s*"([^"]*)"', settings)
check("no JWT secret committed in appsettings.json",
      key is not None and len(key.group(1)) == 0,
      f'Key="{key.group(1)[:30]}..."' if key and key.group(1) else "")

print()
if fails:
    print("RESULT: STRUCTURAL FAILURES ->", fails)
    sys.exit(1)
print("RESULT: ALL STRUCTURAL CHECKS PASSED")
print("NOTE: this is static analysis, not compilation. See TEST-RESULTS.md.")
