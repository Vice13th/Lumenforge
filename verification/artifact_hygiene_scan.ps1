param()
Set-Location (Split-Path -Parent $PSScriptRoot)
$ErrorActionPreference = "Stop"
$forbidden = '\.(RAF|CR2|CR3|NEF|ARW|DNG|ORF|RW2|JPG|JPEG|PNG|WEBP|TIFF|TIF|BMP|MP4|MOV|AVI|MKV|WAV|MP3|ZIP|7Z|RAR|tar|gz|iso|dmp|core|bin|onnx|pt|pth|safetensors|sqlite|db|pkl|npy|npz)$'
$allow = @{}
$allowPath = 'verification\ARTIFACT_ALLOWLIST_20261005.json'
if (Test-Path $allowPath) {
  $obj = Get-Content $allowPath -Raw | ConvertFrom-Json
  foreach($a in $obj.artifacts){ $allow[([IO.Path]::GetFullPath($a.artifact)).ToLowerInvariant()] = $true }
}
$tracked = @(git ls-files)
$trackedForbidden = @($tracked | Where-Object { $_ -match $forbidden })
$trackedLarge = @($tracked | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object { Get-Item -LiteralPath $_ } | Where-Object { $_.Length -gt 5MB })
$generatedTracked = @($tracked | Where-Object { $_ -match '(^|/|\\)(build|dist|\.venv|__pycache__|\.pytest_cache|\.cache|temp|tmp|coverage|htmlcov)(/|\\|$)|\.(obj|o|pdb|ilk|exp|lib|c|cpp)$' })
$untracked = @(git status --porcelain=v1 -uall | Where-Object { $_ -like '?? *' } | ForEach-Object { $_.Substring(3) })
$untrackedForbidden = @($untracked | Where-Object { $_ -match $forbidden } | Where-Object {
  $full=[IO.Path]::GetFullPath($_).ToLowerInvariant()
  -not $allow.ContainsKey($full)
})
$nonBuild = @(Get-ChildItem -Recurse -File -Force -ErrorAction SilentlyContinue | Where-Object { $_.FullName -notmatch '\\\.git(\\|$)|\\build\\|\\\.venv\\|\\\.pytest_cache\\' })
$nonBuildLarge = @($nonBuild | Where-Object { $_.Length -gt 5MB })
$verification = @(Get-ChildItem verification -Recurse -File -Force -ErrorAction SilentlyContinue)
$verificationLarge = @($verification | Where-Object { $_.Length -gt 2MB })
[pscustomobject]@{
 tracked_forbidden=$trackedForbidden.Count
 tracked_gt5mb=$trackedLarge.Count
 tracked_generated=$generatedTracked.Count
 untracked_unallowlisted_forbidden=$untrackedForbidden.Count
 nonbuild_gt5mb=$nonBuildLarge.Count
 verification_gt2mb=$verificationLarge.Count
 status=if(($trackedForbidden.Count+$trackedLarge.Count+$generatedTracked.Count+$untrackedForbidden.Count+$nonBuildLarge.Count+$verificationLarge.Count) -eq 0){'PASS'}else{'FAIL'}
} | Format-List
if($trackedForbidden.Count -or $trackedLarge.Count -or $generatedTracked.Count -or $untrackedForbidden.Count -or $nonBuildLarge.Count -or $verificationLarge.Count){ exit 2 } else { exit 0 }
