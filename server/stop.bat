@echo off
echo Stopping Clef Server processes...
taskkill /F /IM python.exe 2>nul
taskkill /F /IM node.exe 2>nul
echo Done.
