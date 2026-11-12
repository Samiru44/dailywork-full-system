#!/bin/bash
cd "$(dirname "$0")/backend/DailyWork.Api"
echo "============================================================="
echo "  Starting DailyWork"
echo "  First run downloads packages - this may take a minute."
echo "============================================================="
dotnet run
