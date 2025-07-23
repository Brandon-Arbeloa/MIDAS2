# MIDAS Security Incident Response PowerShell Scripts
# Comprehensive automated incident response for Windows 11 deployment

# Import required modules
Import-Module -Name Microsoft.PowerShell.Security -Force -ErrorAction SilentlyContinue
Import-Module -Name EventLog -Force -ErrorAction SilentlyContinue

# Configuration
$Global:MIDAS_CONFIG = @{
    LogPath = "C:\MIDAS\logs\incident_response"
    QuarantinePath = "C:\MIDAS\quarantine"
    BackupPath = "C:\MIDAS\security_backups"
    EmailEnabled = $false
    EmailSMTP = ""
    EmailFrom = ""
    EmailTo = @()
    SlackWebhook = ""
    MaxLogSizeMB = 100
    RetentionDays = 30
}

# Ensure required directories exist
function Initialize-MIDASSecurity {
    param()
    
    $directories = @($Global:MIDAS_CONFIG.LogPath, $Global:MIDAS_CONFIG.QuarantinePath, $Global:MIDAS_CONFIG.BackupPath)
    
    foreach ($dir in $directories) {
        if (-not (Test-Path $dir)) {
            New-Item -Path $dir -ItemType Directory -Force | Out-Null
            Write-Log "Created directory: $dir" -Level "Info"
        }
    }
    
    # Set secure permissions
    foreach ($dir in $directories) {
        try {
            $acl = Get-Acl $dir
            $acl.SetAccessRuleProtection($true, $false)
            
            # Remove all existing rules
            $acl.Access | ForEach-Object { $acl.RemoveAccessRule($_) }
            
            # Add current user with full control
            $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
            $userRule = New-Object System.Security.AccessControl.FileSystemAccessRule($currentUser, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
            $acl.SetAccessRule($userRule)
            
            # Add SYSTEM with full control
            $systemRule = New-Object System.Security.AccessControl.FileSystemAccessRule("NT AUTHORITY\SYSTEM", "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
            $acl.SetAccessRule($systemRule)
            
            Set-Acl -Path $dir -AclObject $acl
        }
        catch {
            Write-Log "Failed to set permissions on $dir : $($_.Exception.Message)" -Level "Error"
        }
    }
}

# Logging function
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "Info",
        [string]$Category = "General"
    )
    
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $logEntry = "$timestamp [$Level] [$Category] $Message"
    
    # Write to console
    switch ($Level) {
        "Error" { Write-Host $logEntry -ForegroundColor Red }
        "Warning" { Write-Host $logEntry -ForegroundColor Yellow }
        "Info" { Write-Host $logEntry -ForegroundColor Green }
        default { Write-Host $logEntry }
    }
    
    # Write to file
    $logFile = Join-Path $Global:MIDAS_CONFIG.LogPath "incident_response_$(Get-Date -Format 'yyyyMMdd').log"
    
    try {
        Add-Content -Path $logFile -Value $logEntry -Encoding UTF8
        
        # Rotate log if too large
        $logSize = (Get-Item $logFile).Length / 1MB
        if ($logSize -gt $Global:MIDAS_CONFIG.MaxLogSizeMB) {
            $rotatedLog = $logFile -replace "\.log$", "_$(Get-Date -Format 'HHmmss').log"
            Rename-Item -Path $logFile -NewName $rotatedLog
        }
    }
    catch {
        Write-Host "Failed to write to log file: $($_.Exception.Message)" -ForegroundColor Red
    }
    
    # Write to Windows Event Log
    try {
        $source = "MIDAS_Security"
        if (-not [System.Diagnostics.EventLog]::SourceExists($source)) {
            New-EventLog -LogName Application -Source $source
        }
        
        $eventType = switch ($Level) {
            "Error" { "Error" }
            "Warning" { "Warning" }
            default { "Information" }
        }
        
        Write-EventLog -LogName Application -Source $source -EventId 1000 -EntryType $eventType -Message $logEntry
    }
    catch {
        # Silently continue if event log write fails
    }
}

# Send alert notifications
function Send-Alert {
    param(
        [string]$Subject,
        [string]$Body,
        [string]$Severity = "Medium"
    )
    
    Write-Log "ALERT [$Severity]: $Subject" -Level "Warning" -Category "Alert"
    
    # Email notification
    if ($Global:MIDAS_CONFIG.EmailEnabled -and $Global:MIDAS_CONFIG.EmailSMTP -and $Global:MIDAS_CONFIG.EmailFrom -and $Global:MIDAS_CONFIG.EmailTo) {
        try {
            $emailSubject = "[MIDAS Security Alert - $Severity] $Subject"
            $emailBody = @"
MIDAS Security Alert

Severity: $Severity
Time: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Host: $env:COMPUTERNAME

$Body

This is an automated alert from the MIDAS security monitoring system.
"@
            
            Send-MailMessage -SmtpServer $Global:MIDAS_CONFIG.EmailSMTP -From $Global:MIDAS_CONFIG.EmailFrom -To $Global:MIDAS_CONFIG.EmailTo -Subject $emailSubject -Body $emailBody
            Write-Log "Email alert sent successfully" -Level "Info" -Category "Alert"
        }
        catch {
            Write-Log "Failed to send email alert: $($_.Exception.Message)" -Level "Error" -Category "Alert"
        }
    }
    
    # Slack notification
    if ($Global:MIDAS_CONFIG.SlackWebhook) {
        try {
            $slackPayload = @{
                text = ":warning: MIDAS Security Alert"
                attachments = @(
                    @{
                        color = switch ($Severity) {
                            "Critical" { "danger" }
                            "High" { "warning" }
                            default { "good" }
                        }
                        fields = @(
                            @{ title = "Severity"; value = $Severity; short = $true }
                            @{ title = "Host"; value = $env:COMPUTERNAME; short = $true }
                            @{ title = "Subject"; value = $Subject; short = $false }
                            @{ title = "Details"; value = $Body; short = $false }
                        )
                        footer = "MIDAS Security"
                        ts = [int][double]::Parse((Get-Date -UFormat %s))
                    }
                )
            } | ConvertTo-Json -Depth 5
            
            Invoke-RestMethod -Uri $Global:MIDAS_CONFIG.SlackWebhook -Method Post -Body $slackPayload -ContentType 'application/json'
            Write-Log "Slack alert sent successfully" -Level "Info" -Category "Alert"
        }
        catch {
            Write-Log "Failed to send Slack alert: $($_.Exception.Message)" -Level "Error" -Category "Alert"
        }
    }
    
    # Windows toast notification
    try {
        $ToastTitle = "MIDAS Security Alert"
        $ToastText = "$Subject`n$Body"
        
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
        [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null
        
        $toastXml = @"
<toast>
    <visual>
        <binding template="ToastGeneric">
            <text>$ToastTitle</text>
            <text>$ToastText</text>
        </binding>
    </visual>
</toast>
"@
        
        $xmlDoc = New-Object Windows.Data.Xml.Dom.XmlDocument
        $xmlDoc.LoadXml($toastXml)
        $toast = New-Object Windows.UI.Notifications.ToastNotification $xmlDoc
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("MIDAS Security").Show($toast)
    }
    catch {
        # Toast notifications may not work in all environments
    }
}

# Quarantine suspicious file
function Invoke-QuarantineFile {
    param(
        [string]$FilePath,
        [string]$Reason = "Suspicious activity detected"
    )
    
    try {
        if (-not (Test-Path $FilePath)) {
            Write-Log "File not found for quarantine: $FilePath" -Level "Warning" -Category "Quarantine"
            return $false
        }
        
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $fileName = [System.IO.Path]::GetFileName($FilePath)
        $quarantineFile = Join-Path $Global:MIDAS_CONFIG.QuarantinePath "${timestamp}_${fileName}"
        
        # Move file to quarantine
        Move-Item -Path $FilePath -Destination $quarantineFile -Force
        
        # Create quarantine metadata
        $metadata = @{
            OriginalPath = $FilePath
            QuarantineTime = Get-Date -Format "o"
            Reason = $Reason
            Host = $env:COMPUTERNAME
            User = $env:USERNAME
        } | ConvertTo-Json -Depth 2
        
        $metadataFile = $quarantineFile + ".metadata"
        Set-Content -Path $metadataFile -Value $metadata -Encoding UTF8
        
        Write-Log "File quarantined: $FilePath -> $quarantineFile" -Level "Info" -Category "Quarantine"
        Send-Alert -Subject "File Quarantined" -Body "File: $FilePath`nReason: $Reason`nQuarantine Location: $quarantineFile" -Severity "Medium"
        
        return $true
    }
    catch {
        Write-Log "Failed to quarantine file $FilePath : $($_.Exception.Message)" -Level "Error" -Category "Quarantine"
        return $false
    }
}

# Kill suspicious process
function Stop-SuspiciousProcess {
    param(
        [int]$ProcessId,
        [string]$ProcessName,
        [string]$Reason = "Suspicious process detected"
    )
    
    try {
        $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        
        if (-not $process) {
            Write-Log "Process not found: PID $ProcessId" -Level "Warning" -Category "Process"
            return $false
        }
        
        Write-Log "Terminating suspicious process: $ProcessName (PID: $ProcessId)" -Level "Info" -Category "Process"
        
        # Try graceful termination first
        $process.CloseMainWindow()
        Start-Sleep -Seconds 3
        
        # Force kill if still running
        if (-not $process.HasExited) {
            Stop-Process -Id $ProcessId -Force
        }
        
        Write-Log "Process terminated: $ProcessName (PID: $ProcessId)" -Level "Info" -Category "Process"
        Send-Alert -Subject "Suspicious Process Terminated" -Body "Process: $ProcessName (PID: $ProcessId)`nReason: $Reason" -Severity "High"
        
        return $true
    }
    catch {
        Write-Log "Failed to terminate process $ProcessId : $($_.Exception.Message)" -Level "Error" -Category "Process"
        return $false
    }
}

# Block suspicious IP address
function Block-SuspiciousIP {
    param(
        [string]$IPAddress,
        [string]$Reason = "Suspicious network activity"
    )
    
    try {
        $ruleName = "MIDAS_Block_$($IPAddress -replace '\.', '_')"
        
        # Check if rule already exists
        $existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
        if ($existingRule) {
            Write-Log "Firewall rule already exists for IP: $IPAddress" -Level "Info" -Category "Firewall"
            return $true
        }
        
        # Create firewall rule to block IP
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Protocol TCP -Action Block -RemoteAddress $IPAddress -Description "MIDAS Security: $Reason"
        New-NetFirewallRule -DisplayName "${ruleName}_Out" -Direction Outbound -Protocol TCP -Action Block -RemoteAddress $IPAddress -Description "MIDAS Security: $Reason"
        
        Write-Log "Blocked suspicious IP: $IPAddress" -Level "Info" -Category "Firewall"
        Send-Alert -Subject "Suspicious IP Blocked" -Body "IP Address: $IPAddress`nReason: $Reason" -Severity "High"
        
        return $true
    }
    catch {
        Write-Log "Failed to block IP $IPAddress : $($_.Exception.Message)" -Level "Error" -Category "Firewall"
        return $false
    }
}

# Collect system information for incident analysis
function Get-IncidentSystemInfo {
    param()
    
    try {
        $systemInfo = @{
            Timestamp = Get-Date -Format "o"
            Hostname = $env:COMPUTERNAME
            Username = $env:USERNAME
            OSVersion = (Get-WmiObject Win32_OperatingSystem).Caption
            Uptime = (Get-Date) - (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
            
            # Process information
            RunningProcesses = Get-Process | Select-Object Name, Id, CPU, WorkingSet, StartTime | Sort-Object CPU -Descending | Select-Object -First 20
            
            # Network connections
            NetworkConnections = Get-NetTCPConnection | Where-Object { $_.State -eq "Established" } | Select-Object LocalAddress, LocalPort, RemoteAddress, RemotePort, OwningProcess
            
            # Recent security events
            SecurityEvents = Get-WinEvent -LogName Security -MaxEvents 50 | Where-Object { $_.LevelDisplayName -eq "Error" -or $_.LevelDisplayName -eq "Warning" }
            
            # System performance
            CPUUsage = (Get-Counter "\Processor(_Total)\% Processor Time").CounterSamples[0].CookedValue
            MemoryUsage = [math]::Round((Get-Counter "\Memory\% Committed Bytes In Use").CounterSamples[0].CookedValue, 2)
            
            # Disk usage
            DiskUsage = Get-WmiObject Win32_LogicalDisk | Select-Object DeviceID, @{Name="Size(GB)";Expression={[math]::Round($_.Size/1GB,2)}}, @{Name="FreeSpace(GB)";Expression={[math]::Round($_.FreeSpace/1GB,2)}}, @{Name="PercentFree";Expression={[math]::Round(($_.FreeSpace/$_.Size)*100,2)}}
            
            # Windows Defender status
            DefenderStatus = Get-MpComputerStatus | Select-Object AntivirusEnabled, RealTimeProtectionEnabled, IoavProtectionEnabled, AntivirusSignatureLastUpdated
            
            # Firewall status
            FirewallStatus = Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction
            
            # Installed software (recent changes)
            RecentSoftware = Get-WmiObject Win32_Product | Where-Object { $_.InstallDate -gt (Get-Date).AddDays(-7).ToString("yyyyMMdd") } | Select-Object Name, Version, InstallDate
        }
        
        $outputFile = Join-Path $Global:MIDAS_CONFIG.LogPath "system_info_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
        $systemInfo | ConvertTo-Json -Depth 5 | Set-Content -Path $outputFile -Encoding UTF8
        
        Write-Log "System information collected: $outputFile" -Level "Info" -Category "Incident"
        
        return $outputFile
    }
    catch {
        Write-Log "Failed to collect system information: $($_.Exception.Message)" -Level "Error" -Category "Incident"
        return $null
    }
}

# Automated malware scan
function Start-MalwareScan {
    param(
        [string]$ScanPath = "C:\",
        [switch]$QuickScan
    )
    
    try {
        Write-Log "Starting malware scan: $ScanPath" -Level "Info" -Category "Scan"
        
        if ($QuickScan) {
            Start-MpScan -ScanType QuickScan
        } else {
            Start-MpScan -ScanType FullScan -ScanPath $ScanPath
        }
        
        # Check scan results
        Start-Sleep -Seconds 5
        $threats = Get-MpThreatDetection
        
        if ($threats) {
            Write-Log "Malware threats detected: $($threats.Count)" -Level "Warning" -Category "Scan"
            
            foreach ($threat in $threats) {
                Write-Log "Threat detected: $($threat.ThreatName) in $($threat.Resources)" -Level "Warning" -Category "Scan"
                Send-Alert -Subject "Malware Detected" -Body "Threat: $($threat.ThreatName)`nLocation: $($threat.Resources)`nSeverity: $($threat.SeverityID)" -Severity "Critical"
            }
            
            # Attempt to remove threats
            Remove-MpThreat
            Write-Log "Attempted to remove detected threats" -Level "Info" -Category "Scan"
        } else {
            Write-Log "Malware scan completed - no threats detected" -Level "Info" -Category "Scan"
        }
        
        return $threats
    }
    catch {
        Write-Log "Malware scan failed: $($_.Exception.Message)" -Level "Error" -Category "Scan"
        return $null
    }
}

# Check for suspicious network activity
function Test-NetworkSecurity {
    param()
    
    try {
        Write-Log "Checking network security" -Level "Info" -Category "Network"
        
        $suspiciousActivity = @()
        
        # Check for unusual outbound connections
        $connections = Get-NetTCPConnection | Where-Object { $_.State -eq "Established" -and $_.RemoteAddress -notlike "192.168.*" -and $_.RemoteAddress -notlike "10.*" -and $_.RemoteAddress -ne "127.0.0.1" }
        
        foreach ($conn in $connections) {
            try {
                $process = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
                if ($process) {
                    $suspiciousActivity += @{
                        Type = "Outbound Connection"
                        LocalAddress = "$($conn.LocalAddress):$($conn.LocalPort)"
                        RemoteAddress = "$($conn.RemoteAddress):$($conn.RemotePort)"
                        Process = $process.ProcessName
                        PID = $conn.OwningProcess
                    }
                }
            }
            catch {
                # Continue if process lookup fails
            }
        }
        
        # Check for processes listening on unusual ports
        $listeners = Get-NetTCPConnection | Where-Object { $_.State -eq "Listen" -and $_.LocalPort -notin @(80, 443, 135, 445, 139, 3389, 5985, 5986) }
        
        foreach ($listener in $listeners) {
            try {
                $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
                if ($process) {
                    $suspiciousActivity += @{
                        Type = "Unusual Listener"
                        LocalAddress = "$($listener.LocalAddress):$($listener.LocalPort)"
                        Process = $process.ProcessName
                        PID = $listener.OwningProcess
                    }
                }
            }
            catch {
                # Continue if process lookup fails
            }
        }
        
        if ($suspiciousActivity.Count -gt 0) {
            Write-Log "Suspicious network activity detected: $($suspiciousActivity.Count) items" -Level "Warning" -Category "Network"
            
            $alertBody = "Suspicious network activities detected:`n`n"
            foreach ($activity in $suspiciousActivity) {
                $alertBody += "Type: $($activity.Type)`n"
                $alertBody += "Process: $($activity.Process) (PID: $($activity.PID))`n"
                if ($activity.LocalAddress) { $alertBody += "Local: $($activity.LocalAddress)`n" }
                if ($activity.RemoteAddress) { $alertBody += "Remote: $($activity.RemoteAddress)`n" }
                $alertBody += "`n"
            }
            
            Send-Alert -Subject "Suspicious Network Activity" -Body $alertBody -Severity "High"
        } else {
            Write-Log "Network security check completed - no suspicious activity" -Level "Info" -Category "Network"
        }
        
        return $suspiciousActivity
    }
    catch {
        Write-Log "Network security check failed: $($_.Exception.Message)" -Level "Error" -Category "Network"
        return $null
    }
}

# Emergency lockdown
function Invoke-EmergencyLockdown {
    param(
        [string]$Reason = "Security incident detected"
    )
    
    try {
        Write-Log "EMERGENCY LOCKDOWN INITIATED: $Reason" -Level "Error" -Category "Emergency"
        Send-Alert -Subject "EMERGENCY LOCKDOWN" -Body "Lockdown initiated due to: $Reason`n`nAll network access blocked and system secured." -Severity "Critical"
        
        # Block all inbound traffic
        New-NetFirewallRule -DisplayName "MIDAS_Emergency_Block_All_In" -Direction Inbound -Protocol Any -Action Block -Profile Any
        
        # Block all outbound traffic except DNS and essential Windows services
        New-NetFirewallRule -DisplayName "MIDAS_Emergency_Block_All_Out" -Direction Outbound -Protocol Any -Action Block -Profile Any
        
        # Allow DNS
        New-NetFirewallRule -DisplayName "MIDAS_Emergency_Allow_DNS" -Direction Outbound -Protocol UDP -LocalPort 53 -Action Allow
        
        # Stop non-essential services
        $servicesToStop = @("Spooler", "Fax", "RemoteRegistry", "Telnet", "SNMP")
        foreach ($service in $servicesToStop) {
            try {
                Stop-Service -Name $service -Force -ErrorAction SilentlyContinue
                Write-Log "Stopped service: $service" -Level "Info" -Category "Emergency"
            }
            catch {
                # Continue if service doesn't exist or can't be stopped
            }
        }
        
        # Create lockdown status file
        $lockdownFile = Join-Path $Global:MIDAS_CONFIG.LogPath "emergency_lockdown.json"
        $lockdownInfo = @{
            Timestamp = Get-Date -Format "o"
            Reason = $Reason
            Host = $env:COMPUTERNAME
            User = $env:USERNAME
            Actions = @(
                "Blocked all inbound traffic",
                "Blocked all outbound traffic (except DNS)",
                "Stopped non-essential services"
            )
        } | ConvertTo-Json -Depth 2
        
        Set-Content -Path $lockdownFile -Value $lockdownInfo -Encoding UTF8
        
        Write-Log "Emergency lockdown completed" -Level "Info" -Category "Emergency"
        return $true
    }
    catch {
        Write-Log "Emergency lockdown failed: $($_.Exception.Message)" -Level "Error" -Category "Emergency"
        return $false
    }
}

# Lift emergency lockdown
function Remove-EmergencyLockdown {
    param()
    
    try {
        Write-Log "Lifting emergency lockdown" -Level "Info" -Category "Emergency"
        
        # Remove emergency firewall rules
        $emergencyRules = Get-NetFirewallRule | Where-Object { $_.DisplayName -like "MIDAS_Emergency_*" }
        foreach ($rule in $emergencyRules) {
            Remove-NetFirewallRule -DisplayName $rule.DisplayName
            Write-Log "Removed emergency rule: $($rule.DisplayName)" -Level "Info" -Category "Emergency"
        }
        
        # Remove lockdown status file
        $lockdownFile = Join-Path $Global:MIDAS_CONFIG.LogPath "emergency_lockdown.json"
        if (Test-Path $lockdownFile) {
            Remove-Item -Path $lockdownFile -Force
        }
        
        Write-Log "Emergency lockdown lifted" -Level "Info" -Category "Emergency"
        Send-Alert -Subject "Emergency Lockdown Lifted" -Body "Emergency lockdown has been lifted. Normal operations can resume." -Severity "Medium"
        
        return $true
    }
    catch {
        Write-Log "Failed to lift emergency lockdown: $($_.Exception.Message)" -Level "Error" -Category "Emergency"
        return $false
    }
}

# Comprehensive security check
function Start-SecurityCheck {
    param(
        [switch]$Full
    )
    
    try {
        Write-Log "Starting security check" -Level "Info" -Category "Security"
        
        $results = @{
            Timestamp = Get-Date -Format "o"
            SystemInfo = $null
            MalwareScan = $null
            NetworkCheck = $null
            Issues = @()
        }
        
        # Collect system information
        $results.SystemInfo = Get-IncidentSystemInfo
        
        # Network security check
        $networkIssues = Test-NetworkSecurity
        if ($networkIssues -and $networkIssues.Count -gt 0) {
            $results.Issues += "Suspicious network activity detected"
            $results.NetworkCheck = $networkIssues
        }
        
        # Malware scan (quick scan unless full requested)
        if ($Full) {
            $threats = Start-MalwareScan
        } else {
            $threats = Start-MalwareScan -QuickScan
        }
        
        if ($threats -and $threats.Count -gt 0) {
            $results.Issues += "Malware threats detected"
            $results.MalwareScan = $threats
        }
        
        # Check Windows Defender status
        try {
            $defenderStatus = Get-MpComputerStatus
            if (-not $defenderStatus.AntivirusEnabled) {
                $results.Issues += "Windows Defender Antivirus is disabled"
            }
            if (-not $defenderStatus.RealTimeProtectionEnabled) {
                $results.Issues += "Windows Defender Real-time protection is disabled"
            }
        }
        catch {
            $results.Issues += "Unable to check Windows Defender status"
        }
        
        # Check firewall status
        try {
            $firewallProfiles = Get-NetFirewallProfile
            foreach ($profile in $firewallProfiles) {
                if (-not $profile.Enabled) {
                    $results.Issues += "Windows Firewall is disabled for $($profile.Name) profile"
                }
            }
        }
        catch {
            $results.Issues += "Unable to check Windows Firewall status"
        }
        
        # Save results
        $resultsFile = Join-Path $Global:MIDAS_CONFIG.LogPath "security_check_$(Get-Date -Format 'yyyyMMdd_HHmmss').json"
        $results | ConvertTo-Json -Depth 5 | Set-Content -Path $resultsFile -Encoding UTF8
        
        if ($results.Issues.Count -gt 0) {
            $alertBody = "Security check completed with issues:`n`n" + ($results.Issues -join "`n")
            Send-Alert -Subject "Security Issues Detected" -Body $alertBody -Severity "High"
            Write-Log "Security check completed with $($results.Issues.Count) issues" -Level "Warning" -Category "Security"
        } else {
            Write-Log "Security check completed - no issues detected" -Level "Info" -Category "Security"
        }
        
        return $results
    }
    catch {
        Write-Log "Security check failed: $($_.Exception.Message)" -Level "Error" -Category "Security"
        return $null
    }
}

# Main incident response orchestration
function Start-IncidentResponse {
    param(
        [string]$IncidentType,
        [hashtable]$IncidentDetails = @{}
    )
    
    try {
        Write-Log "Incident response initiated: $IncidentType" -Level "Warning" -Category "Incident"
        
        $incident = @{
            Id = [System.Guid]::NewGuid().ToString()
            Type = $IncidentType
            StartTime = Get-Date -Format "o"
            Details = $IncidentDetails
            Actions = @()
        }
        
        # Collect initial system information
        $systemInfoFile = Get-IncidentSystemInfo
        if ($systemInfoFile) {
            $incident.Actions += "System information collected: $systemInfoFile"
        }
        
        # Respond based on incident type
        switch ($IncidentType) {
            "MalwareDetected" {
                $threats = Start-MalwareScan -QuickScan
                $incident.Actions += "Malware scan completed"
                
                if ($IncidentDetails.FilePath) {
                    $quarantined = Invoke-QuarantineFile -FilePath $IncidentDetails.FilePath -Reason "Malware detected"
                    if ($quarantined) {
                        $incident.Actions += "Suspicious file quarantined"
                    }
                }
            }
            
            "SuspiciousProcess" {
                if ($IncidentDetails.ProcessId) {
                    $terminated = Stop-SuspiciousProcess -ProcessId $IncidentDetails.ProcessId -ProcessName $IncidentDetails.ProcessName -Reason "Suspicious process behavior"
                    if ($terminated) {
                        $incident.Actions += "Suspicious process terminated"
                    }
                }
            }
            
            "SuspiciousNetwork" {
                $networkIssues = Test-NetworkSecurity
                $incident.Actions += "Network security check completed"
                
                if ($IncidentDetails.IPAddress) {
                    $blocked = Block-SuspiciousIP -IPAddress $IncidentDetails.IPAddress -Reason "Suspicious network activity"
                    if ($blocked) {
                        $incident.Actions += "Suspicious IP address blocked"
                    }
                }
            }
            
            "SecurityBreach" {
                # High-severity incident - consider lockdown
                if ($IncidentDetails.Severity -eq "Critical") {
                    $lockdown = Invoke-EmergencyLockdown -Reason "Security breach detected"
                    if ($lockdown) {
                        $incident.Actions += "Emergency lockdown initiated"
                    }
                }
                
                # Comprehensive security check
                $securityResults = Start-SecurityCheck -Full
                $incident.Actions += "Full security check completed"
            }
            
            default {
                # Generic response
                $networkIssues = Test-NetworkSecurity
                $threats = Start-MalwareScan -QuickScan
                $incident.Actions += "Generic incident response completed"
            }
        }
        
        $incident.EndTime = Get-Date -Format "o"
        $incident.Duration = ([DateTime]$incident.EndTime - [DateTime]$incident.StartTime).TotalMinutes
        
        # Save incident report
        $incidentFile = Join-Path $Global:MIDAS_CONFIG.LogPath "incident_$($incident.Id).json"
        $incident | ConvertTo-Json -Depth 5 | Set-Content -Path $incidentFile -Encoding UTF8
        
        Write-Log "Incident response completed: $IncidentType (ID: $($incident.Id))" -Level "Info" -Category "Incident"
        Send-Alert -Subject "Incident Response Completed" -Body "Incident: $IncidentType`nID: $($incident.Id)`nDuration: $([math]::Round($incident.Duration, 2)) minutes`nActions: $($incident.Actions -join ', ')" -Severity "Medium"
        
        return $incident
    }
    catch {
        Write-Log "Incident response failed: $($_.Exception.Message)" -Level "Error" -Category "Incident"
        return $null
    }
}

# Export functions
Export-ModuleMember -Function *

# Initialize on module load
Initialize-MIDASSecurity

Write-Host "MIDAS Security Incident Response module loaded successfully" -ForegroundColor Green
Write-Host "Available functions:" -ForegroundColor Yellow
Write-Host "  Start-IncidentResponse    - Main incident response function"
Write-Host "  Start-SecurityCheck       - Comprehensive security scan"
Write-Host "  Invoke-EmergencyLockdown  - Emergency system lockdown"
Write-Host "  Remove-EmergencyLockdown  - Lift emergency lockdown"
Write-Host "  Test-NetworkSecurity      - Check for network threats"
Write-Host "  Start-MalwareScan         - Run malware scan"
Write-Host "  Get-IncidentSystemInfo    - Collect system information"