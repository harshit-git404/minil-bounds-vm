# Windows PowerShell Timing & Benchmark Harness for MiniL (Task 10)
# Matches identical protocol and CSV schema as Linux harness:
# - Pin to single CPU core
# - 25 measurement rounds (1 discarded warmup round)
# - Randomly shuffled mode order within each round
# - Output schema: results/timing_raw_windows.csv and results/timing_summary_windows.csv

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

# Pin current PowerShell process to CPU Core 0
try {
    [System.Diagnostics.Process]::GetCurrentProcess().ProcessorAffinity = [IntPtr]1
    Write-Host "Pinned execution to CPU core 0."
} catch {
    Write-Warning "Could not pin CPU affinity: $_"
}

$VmExe = Join-Path $RepoRoot "vm\minil-vm.exe"
if (-not (Test-Path $VmExe)) {
    Write-Error "VM executable not found at $VmExe. Please run scripts/build_windows.sh first."
}

$Modes = @("U", "R", "F", "S", "H", "FS", "FH")
$Rounds = 25
$TmpDir = Join-Path $env:TEMP "minil_windows_bins"
New-Item -ItemType Directory -Force -Path $TmpDir | Out-Null
New-Item -ItemType Directory -Force -Path "results" | Out-Null

$Benchmarks = Get-ChildItem -Path (Join-Path $RepoRoot "benchmarks") -Filter "*.minil" | Sort-Object Name

Write-Host "Compiling benchmarks for all modes..."
$BytecodeMap = @{}

foreach ($bench in $Benchmarks) {
    $bName = $bench.BaseName
    $BytecodeMap[$bName] = @{}
    foreach ($m in $Modes) {
        $mbcPath = Join-Path $TmpDir "$($bName)_$m.mbc"
        $cmd = "python -m compiler.main --mode $m -o `"$mbcPath`" `"$($bench.FullName)`""
        Invoke-Expression $cmd
        $BytecodeMap[$bName][$m] = $mbcPath
    }
}

$RawCsv = "results/timing_raw_windows.csv"
"benchmark,round,mode,time_ns" | Out-File -FilePath $RawCsv -Encoding ascii

$TimingData = @{}

Write-Host "Starting benchmark timing (25 rounds)..."
foreach ($bench in $Benchmarks) {
    $bName = $bench.BaseName
    Write-Host "Timing $bName..."

    # Warmup round
    foreach ($m in $Modes) {
        $mbc = $BytecodeMap[$bName][$m]
        & $VmExe $mbc 2>$null | Out-Null
    }

    # Measurement rounds
    for ($r = 0; $r -lt $Rounds; $r++) {
        $ShuffledModes = $Modes | Get-Random -Count $Modes.Count
        $RoundTimes = @{}

        foreach ($m in $ShuffledModes) {
            $mbc = $BytecodeMap[$bName][$m]
            $procInfo = New-Object System.Diagnostics.ProcessStartInfo
            $procInfo.FileName = $VmExe
            $procInfo.Arguments = "`"$mbc`""
            $procInfo.RedirectStandardError = $true
            $procInfo.RedirectStandardOutput = $true
            $procInfo.UseShellExecute = $false

            $proc = [System.Diagnostics.Process]::Start($procInfo)
            $stderr = $proc.StandardError.ReadToEnd()
            $proc.WaitForExit()

            $tNs = $null
            foreach ($line in ($stderr -split "`r?`n")) {
                if ($line -like "TIME_NS:*") {
                    $tNs = [int64]($line.Split(":")[1].Trim())
                    break
                }
            }

            if ($null -eq $tNs) {
                Write-Error "Failed to get TIME_NS for $bName mode $m round $r"
            }

            $RoundTimes[$m] = $tNs
        }

        foreach ($m in $Modes) {
            "$bName,$r,$m,$($RoundTimes[$m])" | Out-File -FilePath $RawCsv -Append -Encoding ascii
            $key = "$bName,$m"
            if (-not $TimingData.ContainsKey($key)) {
                $TimingData[$key] = [System.Collections.Generic.List[int64]]::new()
            }
            $TimingData[$key].Add($RoundTimes[$m])
        }
    }
}

Write-Host "Computing summary statistics and overhead ratios..."
$SummaryCsv = "results/timing_summary_windows.csv"
"benchmark,mode,median_time_ns,median_ratio,median_overhead_pct,ci_lower_pct,ci_upper_pct" | Out-File -FilePath $SummaryCsv -Encoding ascii

foreach ($bench in $Benchmarks) {
    $bName = $bench.BaseName
    $uTimes = $TimingData["$bName,U"]

    foreach ($m in $Modes) {
        $mTimes = $TimingData["$bName,$m"]
        $sortedM = $mTimes | Sort-Object
        $medTime = $sortedM[[int]($mTimes.Count / 2)]

        $ratios = for ($i = 0; $i -lt $mTimes.Count; $i++) {
            $mTimes[$i] / [double]$uTimes[$i]
        }
        $sortedR = $ratios | Sort-Object
        $medRatio = $sortedR[[int]($ratios.Count / 2)]
        $ovhPct = ($medRatio - 1.0) * 100.0

        # Percentile Bootstrap CI (1000 resamples)
        $bootMedians = [System.Collections.Generic.List[double]]::new()
        $rng = [System.Random]::new(1337)
        for ($b = 0; $b -lt 1000; $b++) {
            $sample = for ($i = 0; $i -lt $ratios.Count; $i++) {
                $ratios[$rng.Next($ratios.Count)]
            }
            $sSorted = $sample | Sort-Object
            $bootMedians.Add(($sSorted[[int]($sample.Count / 2)] - 1.0) * 100.0)
        }
        $sortedBoot = $bootMedians | Sort-Object
        $ciLow = $sortedBoot[25]
        $ciHigh = $sortedBoot[975]

        "$bName,$m,$medTime,$([math]::Round($medRatio, 5)),$([math]::Round($ovhPct, 2)),$([math]::Round($ciLow, 2)),$([math]::Round($ciHigh, 2))" | Out-File -FilePath $SummaryCsv -Append -Encoding ascii
    }
}

Write-Host "Windows benchmarking complete! Output saved to $RawCsv and $SummaryCsv."
