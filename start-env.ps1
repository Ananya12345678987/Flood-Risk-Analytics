# Run with:  . .\start-env.ps1   (note the dot and space)
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
$env:PATH = "$env:JAVA_HOME\bin;E:\hadoop\bin;$env:PATH"
$env:HADOOP_HOME = "E:\hadoop"
$env:SPARK_LOCAL_DIRS = "E:\spark-tmp"
$env:PIP_CACHE_DIR = "E:\pip-cache"
if (-not $env:VIRTUAL_ENV) { .\.venv\Scripts\Activate.ps1 }
Write-Host "Environment ready: Java 17, Hadoop helper, venv active." -ForegroundColor Green
