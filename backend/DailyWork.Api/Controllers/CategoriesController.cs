using DailyWork.Api.Data;
using DailyWork.Api.Dtos;
using DailyWork.Api.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DailyWork.Api.Controllers;

/// <summary>
/// Job categories. The public list is open to everyone so the website can
/// build its sector menus from the database; changing the list is administrator
/// work.
/// </summary>
[ApiController]
[Route("api/categories")]
public class CategoriesController : ControllerBase
{
    private readonly AppDbContext _db;
    public CategoriesController(AppDbContext db) => _db = db;

    /// <summary>GET /api/categories — active categories with a live job count.</summary>
    [HttpGet]
    public async Task<ActionResult> List([FromQuery] bool includeInactive = false)
    {
        var categories = await _db.JobCategories
            .Where(c => includeInactive || c.IsActive)
            .OrderBy(c => c.SortOrder).ThenBy(c => c.Name)
            .ToListAsync();

        var counts = await _db.Jobs
            .Where(j => j.Status == "open")
            .GroupBy(j => j.Category)
            .Select(g => new { Category = g.Key, Count = g.Count() })
            .ToListAsync();

        var result = categories.Select(c => new JobCategoryDto
        {
            Id = c.Id,
            Name = c.Name,
            Description = c.Description,
            Icon = c.Icon,
            SortOrder = c.SortOrder,
            IsActive = c.IsActive,
            OpenJobs = counts.FirstOrDefault(x => x.Category == c.Name)?.Count ?? 0
        }).ToList();

        return Ok(result);
    }

    /// <summary>POST /api/categories</summary>
    [HttpPost]
    [Authorize(Roles = "admin")]
    public async Task<ActionResult> Create([FromBody] JobCategoryWriteDto dto)
    {
        var name = (dto.Name ?? "").Trim();
        if (name.Length < 2)
            return BadRequest(new { message = "Please enter a category name." });

        if (await _db.JobCategories.AnyAsync(c => c.Name.ToLower() == name.ToLower()))
            return Conflict(new { message = "That category already exists." });

        var category = new JobCategory
        {
            Name = name,
            Description = (dto.Description ?? "").Trim(),
            Icon = string.IsNullOrWhiteSpace(dto.Icon) ? "fa-briefcase" : dto.Icon.Trim(),
            SortOrder = dto.SortOrder,
            IsActive = true
        };

        _db.JobCategories.Add(category);
        await _db.SaveChangesAsync();

        return Ok(new { message = "Category added.", id = category.Id });
    }

    /// <summary>PUT /api/categories/5</summary>
    [HttpPut("{id:int}")]
    [Authorize(Roles = "admin")]
    public async Task<ActionResult> Update(int id, [FromBody] JobCategoryWriteDto dto)
    {
        var category = await _db.JobCategories.FindAsync(id);
        if (category is null) return NotFound(new { message = "Category not found." });

        var name = (dto.Name ?? "").Trim();
        if (name.Length < 2)
            return BadRequest(new { message = "Please enter a category name." });

        if (await _db.JobCategories.AnyAsync(c => c.Id != id && c.Name.ToLower() == name.ToLower()))
            return Conflict(new { message = "Another category already uses that name." });

        // Keep existing jobs pointing at the right sector when it is renamed.
        if (!string.Equals(category.Name, name, StringComparison.Ordinal))
        {
            var affected = await _db.Jobs.Where(j => j.Category == category.Name).ToListAsync();
            foreach (var j in affected) j.Category = name;
        }

        category.Name = name;
        category.Description = (dto.Description ?? "").Trim();
        if (!string.IsNullOrWhiteSpace(dto.Icon)) category.Icon = dto.Icon.Trim();
        category.SortOrder = dto.SortOrder;
        if (dto.IsActive.HasValue) category.IsActive = dto.IsActive.Value;

        await _db.SaveChangesAsync();
        return Ok(new { message = "Category updated." });
    }

    /// <summary>
    /// DELETE /api/categories/5
    /// A category still used by jobs is hidden rather than removed, so those
    /// postings keep a sensible sector name.
    /// </summary>
    [HttpDelete("{id:int}")]
    [Authorize(Roles = "admin")]
    public async Task<ActionResult> Delete(int id)
    {
        var category = await _db.JobCategories.FindAsync(id);
        if (category is null) return NotFound(new { message = "Category not found." });

        var inUse = await _db.Jobs.CountAsync(j => j.Category == category.Name);

        if (inUse > 0)
        {
            category.IsActive = false;
            await _db.SaveChangesAsync();
            return Ok(new
            {
                message = $"{inUse} job(s) still use this category, so it was hidden rather than deleted.",
                action = "hidden"
            });
        }

        _db.JobCategories.Remove(category);
        await _db.SaveChangesAsync();
        return Ok(new { message = "Category deleted.", action = "deleted" });
    }
}
