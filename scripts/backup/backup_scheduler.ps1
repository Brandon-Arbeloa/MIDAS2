# MIDAS Windows Backup Scheduler PowerShell Script
# This script sets up Windows Task Scheduler jobs for automated MIDAS backups

param(
    [Parameter(Mandatory=$false)]
    [string]$Action = "install",
    
    [Parameter(Mandatory=$false)]
    [string]$BackupTime = "02:00",
    
    [Parameter(Mandatory=$false)]
    [string]$PythonPath = "python",
    
    [Parameter(Mandatory=$false)]
    [string]$MidasPath = "C:\Users\Rolando Fender\MIDAS",
    
    [Parameter(Mandatory=$false)]
    [string]$LogPath = "C:\Users\Rolando Fender\MIDAS\logs\backup.log"
)

# Ensure running as administrator
if (-NOT ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Error "This script requires Administrator privileges. Please run as Administrator."
    exit 1
}

# Function to create scheduled task
function Install-BackupTask {
    param(
        [string]$TaskName,
        [string]$Description,
        [string]$Schedule,
        [string]$Command,
        [string]$Arguments,
        [string]$WorkingDirectory
    )
    
    Write-Host "Creating scheduled task: $TaskName"
    
    try {
        # Create task action
        $Action = New-ScheduledTaskAction -Execute $Command -Argument $Arguments -WorkingDirectory $WorkingDirectory
        
        # Create task trigger based on schedule
        if ($Schedule -eq "Daily") {
            $Trigger = New-ScheduledTaskTrigger -Daily -At $BackupTime
        } elseif ($Schedule -eq "Weekly") {
            $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "01:00"
        } else {
            Write-Error "Unknown schedule type: $Schedule"
            return
        }
        
        # Create task principal (run as SYSTEM with highest privileges)
        $Principal = New-ScheduledTaskPrincipal -UserID "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
        
        # Create task settings
        $Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable
        
        # Register the task
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description $Description -Force
        
        Write-Host "Successfully created task: $TaskName" -ForegroundColor Green
    }
    catch {
        Write-Error "Failed to create task $TaskName`: $($_.Exception.Message)"
    }
}

# Function to remove scheduled task
function Remove-BackupTask {
    param([string]$TaskName)
    
    Write-Host "Removing scheduled task: $TaskName"
    
    try {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Successfully removed task: $TaskName" -ForegroundColor Green
    }
    catch {
        Write-Warning "Task $TaskName not found or could not be removed: $($_.Exception.Message)"
    }
}

# Function to check if task exists
function Test-TaskExists {
    param([string]$TaskName)
    
    try {
        $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
        return $true
    }
    catch {
        return $false
    }
}

# Main script logic
switch ($Action.ToLower()) {
    "install" {
        Write-Host "Installing MIDAS backup scheduled tasks..." -ForegroundColor Yellow
        
        # Validate paths
        if (-not (Test-Path $MidasPath)) {
            Write-Error "MIDAS path not found: $MidasPath"
            exit 1
        }
        
        # Create logs directory if it doesn't exist
        $LogDir = Split-Path $LogPath -Parent
        if (-not (Test-Path $LogDir)) {
            New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
            Write-Host "Created log directory: $LogDir"
        }
        
        # Task 1: Daily full backup
        $TaskName1 = "MIDAS-DailyBackup"
        $Description1 = "Daily backup of MIDAS RAG system data and configuration"
        $Command1 = $PythonPath
        $Arguments1 = "`"$MidasPath\scripts\backup\windows_backup_manager.py`" --backup postgresql_data --backup qdrant_data --backup application_config --backup user_data"
        
        Install-BackupTask -TaskName $TaskName1 -Description $Description1 -Schedule "Daily" -Command $Command1 -Arguments $Arguments1 -WorkingDirectory $MidasPath
        
        # Task 2: Weekly cleanup
        $TaskName2 = "MIDAS-WeeklyCleanup"
        $Description2 = "Weekly cleanup of old MIDAS backup files"
        $Command2 = $PythonPath
        $Arguments2 = "`"$MidasPath\scripts\backup\windows_backup_manager.py`" --cleanup"
        
        Install-BackupTask -TaskName $TaskName2 -Description $Description2 -Schedule "Weekly" -Command $Command2 -Arguments $Arguments2 -WorkingDirectory $MidasPath
        
        # Task 3: Database-specific backup (every 6 hours)
        $TaskName3 = "MIDAS-DatabaseBackup"
        $Description3 = "Frequent backup of critical database components"
        
        try {
            $Action3 = New-ScheduledTaskAction -Execute $PythonPath -Argument "`"$MidasPath\scripts\backup\windows_backup_manager.py`" --backup postgresql_data --backup qdrant_data" -WorkingDirectory $MidasPath
            $Trigger3 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Hours 6) -RepetitionDuration (New-TimeSpan -Days 365)
            $Principal3 = New-ScheduledTaskPrincipal -UserID "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
            $Settings3 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
            
            Register-ScheduledTask -TaskName $TaskName3 -Action $Action3 -Trigger $Trigger3 -Principal $Principal3 -Settings $Settings3 -Description $Description3 -Force
            Write-Host "Successfully created task: $TaskName3" -ForegroundColor Green
        }
        catch {
            Write-Error "Failed to create task $TaskName3`: $($_.Exception.Message)"
        }
        
        # Create backup status check task (daily)
        $TaskName4 = "MIDAS-BackupHealthCheck"
        $Description4 = "Daily health check of MIDAS backup system"
        $Command4 = "powershell.exe"
        $Arguments4 = "-ExecutionPolicy Bypass -File `"$MidasPath\scripts\backup\backup_health_check.ps1`""
        
        Install-BackupTask -TaskName $TaskName4 -Description $Description4 -Schedule "Daily" -Command $Command4 -Arguments $Arguments4 -WorkingDirectory $MidasPath
        
        Write-Host "`nBackup tasks installed successfully!" -ForegroundColor Green
        Write-Host "Tasks created:" -ForegroundColor Yellow
        Write-Host "  - $TaskName1 (Daily at $BackupTime)"
        Write-Host "  - $TaskName2 (Weekly on Sunday at 01:00)"
        Write-Host "  - $TaskName3 (Every 6 hours)"
        Write-Host "  - $TaskName4 (Daily health check)"
        
        # Display task status
        Write-Host "`nTask Status:" -ForegroundColor Yellow
        Get-ScheduledTask -TaskName "MIDAS-*" | Format-Table TaskName, State, LastRunTime, NextRunTime -AutoSize
    }
    
    "uninstall" {
        Write-Host "Removing MIDAS backup scheduled tasks..." -ForegroundColor Yellow
        
        Remove-BackupTask -TaskName "MIDAS-DailyBackup"
        Remove-BackupTask -TaskName "MIDAS-WeeklyCleanup"
        Remove-BackupTask -TaskName "MIDAS-DatabaseBackup"
        Remove-BackupTask -TaskName "MIDAS-BackupHealthCheck"
        
        Write-Host "`nAll MIDAS backup tasks have been removed." -ForegroundColor Green
    }
    
    "status" {
        Write-Host "MIDAS Backup Task Status:" -ForegroundColor Yellow
        
        $tasks = Get-ScheduledTask -TaskName "MIDAS-*" -ErrorAction SilentlyContinue
        
        if ($tasks) {
            $tasks | ForEach-Object {
                $taskInfo = Get-ScheduledTaskInfo -TaskName $_.TaskName
                
                Write-Host "`nTask: $($_.TaskName)" -ForegroundColor Cyan
                Write-Host "  State: $($_.State)"
                Write-Host "  Last Run: $($taskInfo.LastRunTime)"
                Write-Host "  Last Result: $($taskInfo.LastTaskResult)"
                Write-Host "  Next Run: $($taskInfo.NextRunTime)"
                
                # Get trigger info
                $triggers = $_.Triggers
                if ($triggers) {
                    Write-Host "  Schedule: $($triggers[0].GetType().Name)"
                    if ($triggers[0].StartBoundary) {
                        Write-Host "  Start Time: $($triggers[0].StartBoundary)"
                    }
                    if ($triggers[0].Repetition.Interval) {
                        Write-Host "  Interval: $($triggers[0].Repetition.Interval)"
                    }
                }
            }
        } else {
            Write-Host "No MIDAS backup tasks found." -ForegroundColor Red
        }
    }
    
    "run" {
        Write-Host "Running immediate backup..." -ForegroundColor Yellow
        
        # Run the backup manager directly
        $BackupScript = Join-Path $MidasPath "scripts\backup\windows_backup_manager.py"
        
        if (Test-Path $BackupScript) {
            & $PythonPath $BackupScript --status
            Write-Host "`nStarting immediate backup of all enabled jobs..."
            
            # Run each backup job
            $jobs = @("postgresql_data", "qdrant_data", "application_config", "user_data")
            foreach ($job in $jobs) {
                Write-Host "Backing up: $job" -ForegroundColor Cyan
                & $PythonPath $BackupScript --backup $job
            }
            
            Write-Host "`nImmediate backup completed!" -ForegroundColor Green
        } else {
            Write-Error "Backup script not found: $BackupScript"
        }
    }
    
    "test" {
        Write-Host "Testing backup system..." -ForegroundColor Yellow
        
        # Test Python environment
        try {
            $pythonVersion = & $PythonPath --version 2>&1
            Write-Host "Python version: $pythonVersion" -ForegroundColor Green
        }
        catch {
            Write-Error "Python not found or not working: $PythonPath"
        }
        
        # Test backup script
        $BackupScript = Join-Path $MidasPath "scripts\backup\windows_backup_manager.py"
        if (Test-Path $BackupScript) {
            Write-Host "Backup script found: $BackupScript" -ForegroundColor Green
        } else {
            Write-Error "Backup script not found: $BackupScript"
        }
        
        # Test MIDAS directory structure
        $requiredPaths = @(
            "volumes\postgres-data",
            "volumes\qdrant-storage",
            "volumes\redis-data",
            "backend\core",
            "data"
        )
        
        foreach ($path in $requiredPaths) {
            $fullPath = Join-Path $MidasPath $path
            if (Test-Path $fullPath) {
                Write-Host "✓ $path" -ForegroundColor Green
            } else {
                Write-Warning "✗ $path (not found)"
            }
        }
        
        # Test Windows services
        Write-Host "`nChecking Windows services..." -ForegroundColor Yellow
        $services = @("VSS", "BITS", "Schedule")
        foreach ($service in $services) {
            $svc = Get-Service -Name $service -ErrorAction SilentlyContinue
            if ($svc) {
                Write-Host "✓ $service`: $($svc.Status)" -ForegroundColor Green
            } else {
                Write-Warning "✗ $service (not found)"
            }
        }
        
        Write-Host "`nTest completed!" -ForegroundColor Green
    }
    
    default {
        Write-Host "MIDAS Windows Backup Scheduler" -ForegroundColor Cyan
        Write-Host "Usage: backup_scheduler.ps1 -Action [install|uninstall|status|run|test]" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Actions:" -ForegroundColor Yellow
        Write-Host "  install    - Install scheduled backup tasks"
        Write-Host "  uninstall  - Remove scheduled backup tasks"
        Write-Host "  status     - Show status of backup tasks"
        Write-Host "  run        - Run immediate backup"
        Write-Host "  test       - Test backup system configuration"
        Write-Host ""
        Write-Host "Optional Parameters:" -ForegroundColor Yellow
        Write-Host "  -BackupTime   - Daily backup time (default: 02:00)"
        Write-Host "  -PythonPath   - Path to Python executable (default: python)"
        Write-Host "  -MidasPath    - Path to MIDAS installation (default: C:\Users\Rolando Fender\MIDAS)"
        Write-Host "  -LogPath      - Path for backup logs"
        Write-Host ""
        Write-Host "Examples:" -ForegroundColor Yellow
        Write-Host "  .\backup_scheduler.ps1 -Action install"
        Write-Host "  .\backup_scheduler.ps1 -Action install -BackupTime '03:30'"
        Write-Host "  .\backup_scheduler.ps1 -Action status"
        Write-Host "  .\backup_scheduler.ps1 -Action run"
    }
}

# Exit with success
exit 0