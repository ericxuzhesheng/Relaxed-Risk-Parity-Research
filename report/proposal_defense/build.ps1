$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    New-Item -ItemType Directory -Path '.build' -Force | Out-Null
    foreach ($document in @('proposal_defense', 'proposal_speech')) {
        for ($pass = 1; $pass -le 2; $pass++) {
            & xelatex '-interaction=nonstopmode' '-halt-on-error' '-output-directory=.build' "$document.tex"
            if ($LASTEXITCODE -ne 0) {
                throw "XeLaTeX failed for $document on pass $pass. See .build/$document.log."
            }
        }
        Copy-Item -LiteralPath ".build/$document.pdf" -Destination "$document.pdf" -Force
    }
} finally {
    Pop-Location
}
