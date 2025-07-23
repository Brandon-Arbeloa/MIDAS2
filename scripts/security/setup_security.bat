@echo off
setlocal enabledelayedexpansion

REM MIDAS Security Setup Script for Windows 11
REM Comprehensive security hardening and monitoring setup

echo.
echo ========================================
echo MIDAS Security Setup for Windows 11
echo ========================================
echo.

REM Check for Administrator privileges
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [INFO] Administrator privileges confirmed
) else (
    echo [ERROR] This script requires Administrator privileges
    echo Please run as Administrator
    pause
    exit /b 1
)

REM Create directories
echo [INFO] Creating security directories...
mkdir "C:\MIDAS\logs" 2>nul
mkdir "C:\MIDAS\quarantine" 2>nul
mkdir "C:\MIDAS\security_backups" 2>nul
mkdir "C:\MIDAS\recovery_keys" 2>nul

REM Set secure permissions on directories
echo [INFO] Setting secure permissions...
icacls "C:\MIDAS\quarantine" /inheritance:d /grant "%USERNAME%:(F)" "SYSTEM:(F)" "Administrators:(F)" /remove "Users" "Everyone" >nul 2>&1
icacls "C:\MIDAS\security_backups" /inheritance:d /grant "%USERNAME%:(F)" "SYSTEM:(F)" "Administrators:(F)" /remove "Users" "Everyone" >nul 2>&1
icacls "C:\MIDAS\recovery_keys" /inheritance:d /grant "%USERNAME%:(F)" "SYSTEM:(F)" "Administrators:(F)" /remove "Users" "Everyone" >nul 2>&1

REM Enable Windows Defender if not already enabled
echo [INFO] Configuring Windows Defender...
powershell -Command "Set-MpPreference -DisableRealtimeMonitoring $false" >nul 2>&1
powershell -Command "Update-MpSignature" >nul 2>&1

REM Configure Windows Firewall
echo [INFO] Configuring Windows Firewall...
netsh advfirewall set allprofiles state on >nul 2>&1
netsh advfirewall set allprofiles firewallpolicy blockinbound,allowoutbound >nul 2>&1

REM Enable firewall logging
netsh advfirewall set allprofiles logging filename "C:\Windows\System32\LogFiles\Firewall\pfirewall.log" >nul 2>&1
netsh advfirewall set allprofiles logging maxfilesize 4096 >nul 2>&1
netsh advfirewall set allprofiles logging droppedconnections enable >nul 2>&1

REM Allow MIDAS application ports
echo [INFO] Configuring MIDAS application firewall rules...
netsh advfirewall firewall add rule name="MIDAS FastAPI" dir=in action=allow protocol=TCP localport=8000 >nul 2>&1
netsh advfirewall firewall add rule name="MIDAS Streamlit" dir=in action=allow protocol=TCP localport=8501 >nul 2>&1
netsh advfirewall firewall add rule name="MIDAS PostgreSQL Local" dir=in action=allow protocol=TCP localport=5432 remoteip=127.0.0.1 >nul 2>&1
netsh advfirewall firewall add rule name="MIDAS Redis Local" dir=in action=allow protocol=TCP localport=6379 remoteip=127.0.0.1 >nul 2>&1

REM Block common attack ports
echo [INFO] Blocking dangerous ports...
netsh advfirewall firewall add rule name="Block Telnet" dir=in action=block protocol=TCP localport=23 >nul 2>&1
netsh advfirewall firewall add rule name="Block SNMP" dir=in action=block protocol=UDP localport=161 >nul 2>&1
netsh advfirewall firewall add rule name="Block NetBIOS" dir=in action=block protocol=UDP localport=137,138 >nul 2>&1
netsh advfirewall firewall add rule name="Block SMB" dir=in action=block protocol=TCP localport=445 >nul 2>&1

REM Configure Windows Event Log
echo [INFO] Configuring Windows Event Logging...
wevtutil sl Security /ms:102400000 >nul 2>&1
wevtutil sl Application /ms:102400000 >nul 2>&1
wevtutil sl System /ms:102400000 >nul 2>&1

REM Enable audit policies
echo [INFO] Enabling security audit policies...
auditpol /set /category:"Logon/Logoff" /success:enable /failure:enable >nul 2>&1
auditpol /set /category:"Account Logon" /success:enable /failure:enable >nul 2>&1
auditpol /set /category:"Account Management" /success:enable /failure:enable >nul 2>&1
auditpol /set /category:"Policy Change" /success:enable /failure:enable >nul 2>&1
auditpol /set /category:"System" /success:enable /failure:enable >nul 2>&1

REM Disable unnecessary services
echo [INFO] Disabling unnecessary services...
sc config "Fax" start= disabled >nul 2>&1
sc config "Telnet" start= disabled >nul 2>&1
sc config "RemoteRegistry" start= disabled >nul 2>&1
sc config "SSDPSRV" start= disabled >nul 2>&1

REM Configure registry security settings
echo [INFO] Applying security registry settings...
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Lsa" /v "RestrictAnonymous" /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Lsa" /v "RestrictAnonymousSAM" /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SYSTEM\CurrentControlSet\Control\Lsa" /v "LimitBlankPasswordUse" /t REG_DWORD /d 1 /f >nul 2>&1
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System" /v "EnableLUA" /t REG_DWORD /d 1 /f >nul 2>&1

REM Configure PowerShell execution policy for security scripts
echo [INFO] Configuring PowerShell execution policy...
powershell -Command "Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope LocalMachine -Force" >nul 2>&1

REM Install required Python packages
echo [INFO] Installing required Python packages...
if exist "C:\Users\Rolando Fender\MIDAS\scripts\security\security_automation.py" (
    python -m pip install --quiet psutil pywin32 requests win10toast 2>nul
    if !errorlevel! equ 0 (
        echo [INFO] Python packages installed successfully
    ) else (
        echo [WARNING] Some Python packages may not have installed correctly
    )
) else (
    echo [WARNING] Security automation script not found
)

REM Create Windows Task for automated security monitoring
echo [INFO] Creating automated security monitoring task...
schtasks /create /tn "MIDAS Security Monitor" /tr "python \"C:\Users\Rolando Fender\MIDAS\scripts\security\security_automation.py\" --start" /sc onstart /ru SYSTEM /f >nul 2>&1

REM Register MIDAS security event source
echo [INFO] Registering Windows Event Log source...
powershell -Command "New-EventLog -LogName Application -Source 'MIDAS_Security' -ErrorAction SilentlyContinue" >nul 2>&1

REM Create security configuration file
echo [INFO] Creating security configuration file...
(
echo {
echo   "monitoring_interval": 60,
echo   "enable_email_alerts": false,
echo   "email_smtp_server": "",
echo   "email_smtp_port": 587,
echo   "email_username": "",
echo   "email_password": "",
echo   "email_recipients": [],
echo   "slack_webhook_url": "",
echo   "max_cpu_threshold": 90,
echo   "max_memory_threshold": 90,
echo   "max_failed_logins": 5,
echo   "quarantine_directory": "C:/MIDAS/quarantine",
echo   "backup_directory": "C:/MIDAS/security_backups",
echo   "log_directory": "C:/MIDAS/logs",
echo   "enable_auto_response": true,
echo   "powershell_script_path": "C:/Users/Rolando Fender/MIDAS/scripts/security/incident_response.ps1"
echo }
) > "C:\MIDAS\security_config.json"

REM Create startup script
echo [INFO] Creating security startup script...
(
echo @echo off
echo echo Starting MIDAS Security Services...
echo.
echo REM Start security monitoring
echo python "C:\Users\Rolando Fender\MIDAS\scripts\security\security_automation.py" --start
echo.
echo REM Load PowerShell incident response module
echo powershell -Command "Import-Module 'C:\Users\Rolando Fender\MIDAS\scripts\security\incident_response.ps1' -Force"
echo.
echo echo MIDAS Security Services started successfully.
echo pause
) > "C:\MIDAS\start_security.bat"

REM Run initial security scan
echo [INFO] Running initial security scan...
if exist "C:\Users\Rolando Fender\MIDAS\scripts\security\security_automation.py" (
    python "C:\Users\Rolando Fender\MIDAS\scripts\security\security_automation.py" --scan >nul 2>&1
)

REM Create security report
echo [INFO] Generating security setup report...
(
echo MIDAS Security Setup Report
echo Generated: %date% %time%
echo.
echo [DIRECTORIES]
echo - Logs: C:\MIDAS\logs
echo - Quarantine: C:\MIDAS\quarantine
echo - Backups: C:\MIDAS\security_backups
echo - Recovery Keys: C:\MIDAS\recovery_keys
echo.
echo [WINDOWS DEFENDER]
) > "C:\MIDAS\security_setup_report.txt"

powershell -Command "Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, IoavProtectionEnabled | Format-List" >> "C:\MIDAS\security_setup_report.txt" 2>nul

echo. >> "C:\MIDAS\security_setup_report.txt"
echo [WINDOWS FIREWALL] >> "C:\MIDAS\security_setup_report.txt"
powershell -Command "Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction | Format-Table -AutoSize" >> "C:\MIDAS\security_setup_report.txt" 2>nul

echo. >> "C:\MIDAS\security_setup_report.txt"
echo [AUDIT POLICIES] >> "C:\MIDAS\security_setup_report.txt"
auditpol /get /category:* | findstr "Success and Failure" >> "C:\MIDAS\security_setup_report.txt" 2>nul

echo.
echo ========================================
echo Security Setup Complete!
echo ========================================
echo.
echo Setup report saved to: C:\MIDAS\security_setup_report.txt
echo Configuration file: C:\MIDAS\security_config.json
echo.
echo To start security monitoring:
echo   1. Run: C:\MIDAS\start_security.bat
echo   2. Or use: python security_automation.py --start
echo.
echo To check status:
echo   python security_automation.py --status
echo.
echo To run manual security scan:
echo   python security_automation.py --scan
echo.

REM Check if reboot is recommended
echo [INFO] Checking if reboot is required...
if exist "%SystemRoot%\System32\Tasks\MIDAS Security Monitor" (
    echo [INFO] Security task created successfully
) else (
    echo [WARNING] Security task may not have been created properly
)

echo Press any key to view the security setup report...
pause >nul

type "C:\MIDAS\security_setup_report.txt"

echo.
echo Setup completed successfully!
echo Some changes may require a system restart to take full effect.
echo.
pause