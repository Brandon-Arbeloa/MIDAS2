# Test-Ollama.ps1
# Comprehensive Ollama API testing and performance measurement for Windows 11
# Usage: .\Test-Ollama.ps1 -Model "llama3.2:3b" -TestIterations 3

param(
    [string]$OllamaUrl = "http://localhost:11434",
    [string]$Model = "llama3.2:3b",
    [int]$TestIterations = 3,
    [switch]$Detailed = $false
)

Write-Host "=== Ollama API Test Suite ===" -ForegroundColor Green
Write-Host "URL: $OllamaUrl" -ForegroundColor Yellow
Write-Host "Model: $Model" -ForegroundColor Yellow
Write-Host "Iterations: $TestIterations" -ForegroundColor Yellow
Write-Host ""

# Create log directory if it doesn't exist
$logDir = "C:\Ollama\logs"
if (!(Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
}

# Test 1: Service Connectivity
Write-Host "1. Testing API Connectivity..." -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri "$OllamaUrl/api/version" -Method Get -TimeoutSec 10
    Write-Host "✅ API accessible - Version: $($response.version)" -ForegroundColor Green
} catch {
    Write-Host "❌ API not accessible: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "💡 Make sure Ollama is running: ollama serve" -ForegroundColor Yellow
    exit 1
}

# Test 2: Model Availability
Write-Host "`n2. Checking Model Availability..." -ForegroundColor Cyan
try {
    $models = Invoke-RestMethod -Uri "$OllamaUrl/api/tags" -Method Get -TimeoutSec 15
    $availableModel = $models.models | Where-Object { $_.name -eq $Model }
    if ($availableModel) {
        Write-Host "✅ Model '$Model' is available" -ForegroundColor Green
        Write-Host "   Size: $([math]::Round($availableModel.size / 1GB, 2)) GB" -ForegroundColor Gray
        Write-Host "   Modified: $($availableModel.modified_at)" -ForegroundColor Gray
    } else {
        Write-Host "❌ Model '$Model' not found" -ForegroundColor Red
        Write-Host "Available models:" -ForegroundColor Yellow
        $models.models | ForEach-Object { Write-Host "  - $($_.name) ($([math]::Round($_.size / 1GB, 2)) GB)" -ForegroundColor Gray }
        Write-Host "`n💡 To install the model, run: ollama pull $Model" -ForegroundColor Yellow
        exit 1
    }
} catch {
    Write-Host "❌ Failed to check models: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# Test 3: System Resource Check
Write-Host "`n3. System Resource Analysis..." -ForegroundColor Cyan
$ram = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB
$cpu = (Get-CimInstance Win32_Processor).Name
$cores = (Get-CimInstance Win32_Processor).NumberOfCores
$logicalCores = (Get-CimInstance Win32_Processor).NumberOfLogicalProcessors

Write-Host "💻 CPU: $cpu" -ForegroundColor Gray
Write-Host "🔢 Cores: $cores physical, $logicalCores logical" -ForegroundColor Gray
Write-Host "🧠 RAM: $([math]::Round($ram, 1)) GB total" -ForegroundColor Gray

# Check available memory
$availableMemory = (Get-Counter '\Memory\Available MBytes').CounterSamples.CookedValue / 1024
Write-Host "💾 Available RAM: $([math]::Round($availableMemory, 1)) GB" -ForegroundColor Gray

if ($ram -lt 8) {
    Write-Host "⚠️  Warning: Less than 8GB RAM detected. Performance may be limited." -ForegroundColor Yellow
} elseif ($ram -ge 16) {
    Write-Host "✅ Excellent RAM for optimal LLM performance" -ForegroundColor Green
} else {
    Write-Host "✅ Adequate RAM for good LLM performance" -ForegroundColor Green
}

# Test 4: Performance Benchmarks
Write-Host "`n4. Running Performance Tests ($TestIterations iterations)..." -ForegroundColor Cyan

$testPrompts = @(
    @{Text = "Hello, how are you?"; Category = "Simple"},
    @{Text = "Explain quantum computing in simple terms."; Category = "Explanatory"},
    @{Text = "Write a Python function to calculate fibonacci numbers."; Category = "Coding"},
    @{Text = "Summarize the key benefits of renewable energy sources."; Category = "Analytical"}
)

$results = @()
$totalTests = $testPrompts.Count * $TestIterations

$currentTest = 0
foreach ($prompt in $testPrompts) {
    Write-Host "`nTesting $($prompt.Category) prompt: '$($prompt.Text.Substring(0, [Math]::Min(50, $prompt.Text.Length)))...'" -ForegroundColor Yellow
    
    for ($i = 1; $i -le $TestIterations; $i++) {
        $currentTest++
        $progress = [math]::Round(($currentTest / $totalTests) * 100, 1)
        Write-Host "  Iteration $i/$TestIterations ($progress%)..." -NoNewline
        
        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        
        try {
            $body = @{
                model = $Model
                prompt = $prompt.Text
                stream = $false
                options = @{
                    num_predict = 150
                    temperature = 0.7
                    top_p = 0.9
                    num_ctx = 2048
                }
            } | ConvertTo-Json -Depth 3
            
            $response = Invoke-RestMethod -Uri "$OllamaUrl/api/generate" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 120
            
            $stopwatch.Stop()
            $responseTime = $stopwatch.ElapsedMilliseconds
            
            # Calculate tokens per second (approximate)
            $tokenCount = ($response.response -split '\s+').Count
            $tokensPerSecond = if ($responseTime -gt 0) { [math]::Round($tokenCount / ($responseTime / 1000), 2) } else { 0 }
            
            # Calculate time to first token (TTFT) - approximation
            $ttft = [math]::Round($responseTime / 10, 2)  # Rough estimate
            
            $results += [PSCustomObject]@{
                Category = $prompt.Category
                Prompt = $prompt.Text.Substring(0, [Math]::Min(50, $prompt.Text.Length)) + "..."
                Iteration = $i
                ResponseTime = $responseTime
                TokenCount = $tokenCount
                TokensPerSecond = $tokensPerSecond
                TTFT = $ttft
                Success = $true
                ResponsePreview = $response.response.Substring(0, [Math]::Min(100, $response.response.Length)) + "..."
                TotalDuration = $response.total_duration
                LoadDuration = $response.load_duration
                PromptEvalDuration = $response.prompt_eval_duration
            }
            
            Write-Host " ✅ ${responseTime}ms ($tokensPerSecond tok/s)" -ForegroundColor Green
            
            if ($Detailed) {
                Write-Host "    Response preview: $($response.response.Substring(0, [Math]::Min(80, $response.response.Length)))..." -ForegroundColor DarkGray
            }
            
        } catch {
            $stopwatch.Stop()
            Write-Host " ❌ Error: $($_.Exception.Message.Substring(0, [Math]::Min(50, $_.Exception.Message.Length)))" -ForegroundColor Red
            
            $results += [PSCustomObject]@{
                Category = $prompt.Category
                Prompt = $prompt.Text.Substring(0, [Math]::Min(50, $prompt.Text.Length)) + "..."
                Iteration = $i
                ResponseTime = $null
                TokenCount = $null
                TokensPerSecond = $null
                TTFT = $null
                Success = $false
                Error = $_.Exception.Message
                ResponsePreview = $null
                TotalDuration = $null
                LoadDuration = $null
                PromptEvalDuration = $null
            }
        }
        
        # Brief pause between requests to avoid overwhelming the service
        Start-Sleep -Milliseconds 500
    }
}

# Test Results Analysis
Write-Host "`n=== Performance Analysis ===" -ForegroundColor Green

$successfulTests = $results | Where-Object { $_.Success -eq $true }
$failedTests = $results | Where-Object { $_.Success -eq $false }

if ($successfulTests.Count -gt 0) {
    # Overall Statistics
    $avgResponseTime = ($successfulTests | Measure-Object ResponseTime -Average).Average
    $medianResponseTime = ($successfulTests | Sort-Object ResponseTime)[[math]::Floor($successfulTests.Count / 2)].ResponseTime
    $avgTokensPerSecond = ($successfulTests | Measure-Object TokensPerSecond -Average).Average
    $maxTokensPerSecond = ($successfulTests | Measure-Object TokensPerSecond -Maximum).Maximum
    $minTokensPerSecond = ($successfulTests | Measure-Object TokensPerSecond -Minimum).Minimum
    
    Write-Host "✅ Success Rate: $($successfulTests.Count)/$($results.Count) ($([math]::Round(($successfulTests.Count / $results.Count) * 100, 1))%)" -ForegroundColor Green
    Write-Host ""
    Write-Host "📊 Response Time Statistics:" -ForegroundColor Cyan
    Write-Host "   Average: $([math]::Round($avgResponseTime, 2))ms" -ForegroundColor White
    Write-Host "   Median:  $([math]::Round($medianResponseTime, 2))ms" -ForegroundColor White
    Write-Host "   Range:   $([math]::Round(($successfulTests | Measure-Object ResponseTime -Minimum).Minimum, 2))ms - $([math]::Round(($successfulTests | Measure-Object ResponseTime -Maximum).Maximum, 2))ms" -ForegroundColor White
    Write-Host ""
    Write-Host "🚀 Throughput Statistics:" -ForegroundColor Cyan
    Write-Host "   Average: $([math]::Round($avgTokensPerSecond, 2)) tokens/sec" -ForegroundColor White
    Write-Host "   Peak:    $([math]::Round($maxTokensPerSecond, 2)) tokens/sec" -ForegroundColor White
    Write-Host "   Lowest:  $([math]::Round($minTokensPerSecond, 2)) tokens/sec" -ForegroundColor White
    
    # Performance by Category
    Write-Host ""
    Write-Host "📈 Performance by Category:" -ForegroundColor Cyan
    $categoryStats = $successfulTests | Group-Object Category | ForEach-Object {
        $avgTime = ($_.Group | Measure-Object ResponseTime -Average).Average
        $avgThroughput = ($_.Group | Measure-Object TokensPerSecond -Average).Average
        [PSCustomObject]@{
            Category = $_.Name
            Tests = $_.Count
            AvgResponseTime = [math]::Round($avgTime, 2)
            AvgThroughput = [math]::Round($avgThroughput, 2)
        }
    }
    
    $categoryStats | ForEach-Object {
        Write-Host "   $($_.Category): $($_.AvgResponseTime)ms, $($_.AvgThroughput) tok/s ($($_.Tests) tests)" -ForegroundColor White
    }
    
} else {
    Write-Host "❌ No successful tests completed" -ForegroundColor Red
    if ($failedTests.Count -gt 0) {
        Write-Host "Error summary:" -ForegroundColor Yellow
        $failedTests | Group-Object Error | ForEach-Object {
            Write-Host "  - $($_.Name) ($($_.Count) occurrences)" -ForegroundColor Red
        }
    }
}

# Performance Recommendations
Write-Host "`n=== Recommendations ===" -ForegroundColor Green

if ($successfulTests.Count -gt 0) {
    $avgThroughput = ($successfulTests | Measure-Object TokensPerSecond -Average).Average
    
    if ($avgThroughput -lt 5) {
        Write-Host "🔧 Consider optimizing Ollama settings for better performance:" -ForegroundColor Yellow
        Write-Host "   - Reduce num_ctx to 1024 for faster responses" -ForegroundColor Gray
        Write-Host "   - Lower num_predict to 100 for shorter responses" -ForegroundColor Gray
        Write-Host "   - Try a smaller model like phi3:mini" -ForegroundColor Gray
    } elseif ($avgThroughput -gt 20) {
        Write-Host "🎯 Excellent performance! Consider:" -ForegroundColor Green
        Write-Host "   - Increasing num_ctx for longer context" -ForegroundColor Gray
        Write-Host "   - Using larger models for better quality" -ForegroundColor Gray
    } else {
        Write-Host "✅ Good performance balance achieved" -ForegroundColor Green
    }
}

if ($availableMemory -lt 4) {
    Write-Host "⚠️  Low available memory. Close other applications for better performance." -ForegroundColor Yellow
}

# Save detailed results
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$resultsFile = "$logDir\ollama-test-results-$timestamp.json"
$summaryFile = "$logDir\ollama-test-summary-$timestamp.txt"

# Save JSON results
$testReport = @{
    Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    SystemInfo = @{
        CPU = $cpu
        Cores = $cores
        LogicalCores = $logicalCores
        TotalRAM = [math]::Round($ram, 1)
        AvailableRAM = [math]::Round($availableMemory, 1)
    }
    TestConfiguration = @{
        OllamaUrl = $OllamaUrl
        Model = $Model
        Iterations = $TestIterations
        TotalTests = $results.Count
    }
    Results = $results
    Summary = @{
        SuccessRate = if ($results.Count -gt 0) { [math]::Round(($successfulTests.Count / $results.Count) * 100, 2) } else { 0 }
        AverageResponseTime = if ($successfulTests.Count -gt 0) { [math]::Round(($successfulTests | Measure-Object ResponseTime -Average).Average, 2) } else { $null }
        AverageThroughput = if ($successfulTests.Count -gt 0) { [math]::Round(($successfulTests | Measure-Object TokensPerSecond -Average).Average, 2) } else { $null }
        CategoryStats = $categoryStats
    }
}

$testReport | ConvertTo-Json -Depth 5 | Out-File $resultsFile -Encoding UTF8

# Save readable summary
@"
OLLAMA PERFORMANCE TEST SUMMARY
================================
Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Model: $Model
Total Tests: $($results.Count)
Success Rate: $($testReport.Summary.SuccessRate)%

SYSTEM INFO:
- CPU: $cpu
- RAM: $([math]::Round($ram, 1)) GB total, $([math]::Round($availableMemory, 1)) GB available
- Cores: $cores physical, $logicalCores logical

PERFORMANCE METRICS:
- Average Response Time: $($testReport.Summary.AverageResponseTime)ms
- Average Throughput: $($testReport.Summary.AverageThroughput) tokens/sec
- Peak Throughput: $([math]::Round($maxTokensPerSecond, 2)) tokens/sec

CATEGORY BREAKDOWN:
$($categoryStats | ForEach-Object { "- $($_.Category): $($_.AvgResponseTime)ms, $($_.AvgThroughput) tok/s" } | Out-String)

FILES GENERATED:
- Detailed Results: $resultsFile
- Summary Report: $summaryFile
"@ | Out-File $summaryFile -Encoding UTF8

Write-Host "`n📁 Results saved to:" -ForegroundColor Gray
Write-Host "   📊 Detailed: $resultsFile" -ForegroundColor Gray
Write-Host "   📋 Summary:  $summaryFile" -ForegroundColor Gray

Write-Host "`n=== Test Complete ===" -ForegroundColor Green

# Return exit code based on test results
if ($failedTests.Count -eq 0) {
    exit 0
} else {
    exit 1
}