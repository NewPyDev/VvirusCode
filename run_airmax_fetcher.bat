@echo off
REM ─── AirMax TV Weekly Code Fetcher ───
REM Scheduled via Windows Task Scheduler — every Sunday at 03:00 AM
REM (code updates between 00:30-02:30 Europe time)

cd /d "d:\PythonProjects\VvirusCode"
python airmax_code_fetcher.py
