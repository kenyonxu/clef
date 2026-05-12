@echo off
set HTTP_PROXY=http://127.0.0.1:10080
set HTTPS_PROXY=http://127.0.0.1:10080
echo Proxy: %HTTP_PROXY%
codex %*
