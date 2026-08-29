@echo off
rem Verify a Gauntlet II secret-room contest code with uv.
rem
rem   verify-secret-code.bat "ALINSA" FB9-AD9

cd /d "%~dp0"
set "UV_LINK_MODE=copy"

uv run python -m gauntpy.secret_code_verifier %*
