@echo off
echo =======================================================
echo Running Drone Footprint 3D Ray-Casting Pipeline...
echo =======================================================
cd /d "d:\DRDO\drone points"
py -3.10 "d:\DRDO\drone points\footprint_pipeline\run_pipeline.py"
pause
