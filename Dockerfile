# Build the ASP.NET Core 10 API and copy its bundled wwwroot frontend.
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY backend/DailyWork.Api/DailyWork.Api.csproj backend/DailyWork.Api/
RUN dotnet restore backend/DailyWork.Api/DailyWork.Api.csproj
COPY . .
RUN dotnet publish backend/DailyWork.Api/DailyWork.Api.csproj -c Release --no-restore -o /app/publish /p:UseAppHost=false

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
ENV ASPNETCORE_ENVIRONMENT=Production
COPY --from=build /app/publish .
EXPOSE 10000
ENTRYPOINT ["dotnet", "DailyWork.Api.dll"]
