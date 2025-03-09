@echo off
setlocal

REM 设置命令提示符使用UTF-8编码
chcp 65001 > nul

set MASTER_DOMAIN_NAME=pc75.cloudlab.umass.edu
set WORKER1_DOMAIN_NAME=pc74.cloudlab.umass.edu
set WORKER2_DOMAIN_NAME=pc98.cloudlab.umass.edu
set WORKER3_DOMAIN_NAME=pc63.cloudlab.umass.edu
set WORKER4_DOMAIN_NAME=pc83.cloudlab.umass.edu

REM 定义要发送的文件夹路径
set source_dir=D:\adaptation\muBench\Experiment
set target_dir=~/Experiment
set USERNAME=Dingjie

REM 更新master.sh和worker.sh和tc.sh中的域名变量
echo 正在更新脚本中的域名变量...

REM 创建临时文件
type "%source_dir%\master.sh" > "%source_dir%\master.sh.tmp"
type "%source_dir%\worker.sh" > "%source_dir%\worker.sh.tmp"
type "%source_dir%\tc.sh" > "%source_dir%\tc.sh.tmp"

REM 使用PowerShell进行文本替换，并确保使用UTF-8编码
powershell -Command "$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'; (Get-Content '%source_dir%\master.sh.tmp' -Encoding utf8) -replace 'MASTER_DOMAIN_NAME=\".*\"', 'MASTER_DOMAIN_NAME=\"%MASTER_DOMAIN_NAME%\"' -replace 'WORKER1_DOMAIN_NAME=\".*\"', 'WORKER1_DOMAIN_NAME=\"%WORKER1_DOMAIN_NAME%\"' -replace 'WORKER2_DOMAIN_NAME=\".*\"', 'WORKER2_DOMAIN_NAME=\"%WORKER2_DOMAIN_NAME%\"' -replace 'WORKER3_DOMAIN_NAME=\".*\"', 'WORKER3_DOMAIN_NAME=\"%WORKER3_DOMAIN_NAME%\"' -replace 'WORKER4_DOMAIN_NAME=\".*\"', 'WORKER4_DOMAIN_NAME=\"%WORKER4_DOMAIN_NAME%\"' | Out-File '%source_dir%\master.sh' -Encoding utf8"
powershell -Command "$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'; (Get-Content '%source_dir%\worker.sh.tmp' -Encoding utf8) -replace 'MASTER_DOMAIN_NAME=\".*\"', 'MASTER_DOMAIN_NAME=\"%MASTER_DOMAIN_NAME%\"' -replace 'WORKER1_DOMAIN_NAME=\".*\"', 'WORKER1_DOMAIN_NAME=\"%WORKER1_DOMAIN_NAME%\"' -replace 'WORKER2_DOMAIN_NAME=\".*\"', 'WORKER2_DOMAIN_NAME=\"%WORKER2_DOMAIN_NAME%\"' -replace 'WORKER3_DOMAIN_NAME=\".*\"', 'WORKER3_DOMAIN_NAME=\"%WORKER3_DOMAIN_NAME%\"' -replace 'WORKER4_DOMAIN_NAME=\".*\"', 'WORKER4_DOMAIN_NAME=\"%WORKER4_DOMAIN_NAME%\"' | Out-File '%source_dir%\worker.sh' -Encoding utf8"
REM 替换tc.sh中的域名变量
powershell -Command "$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'; (Get-Content '%source_dir%\tc.sh.tmp' -Encoding utf8) -replace 'MASTER_DOMAIN_NAME=\".*\"', 'MASTER_DOMAIN_NAME=\"%MASTER_DOMAIN_NAME%\"' -replace 'WORKER1_DOMAIN_NAME=\".*\"', 'WORKER1_DOMAIN_NAME=\"%WORKER1_DOMAIN_NAME%\"' -replace 'WORKER2_DOMAIN_NAME=\".*\"', 'WORKER2_DOMAIN_NAME=\"%WORKER2_DOMAIN_NAME%\"' -replace 'WORKER3_DOMAIN_NAME=\".*\"', 'WORKER3_DOMAIN_NAME=\"%WORKER3_DOMAIN_NAME%\"' -replace 'WORKER4_DOMAIN_NAME=\".*\"', 'WORKER4_DOMAIN_NAME=\"%WORKER4_DOMAIN_NAME%\"' | Out-File '%source_dir%\tc.sh' -Encoding utf8"
   
REM 删除临时文件  
del "%source_dir%\master.sh.tmp"
del "%source_dir%\worker.sh.tmp"
del "%source_dir%\tc.sh.tmp"

REM 转换文件为Unix格式（LF换行符），同时保持UTF-8编码
echo 正在转换脚本为Unix格式...
powershell -Command "$content = [System.IO.File]::ReadAllText('%source_dir%\master.sh').Replace(\"`r`n\", \"`n\"); [System.IO.File]::WriteAllText('%source_dir%\master.sh', $content, [System.Text.Encoding]::UTF8)"
powershell -Command "$content = [System.IO.File]::ReadAllText('%source_dir%\worker.sh').Replace(\"`r`n\", \"`n\"); [System.IO.File]::WriteAllText('%source_dir%\worker.sh', $content, [System.Text.Encoding]::UTF8)"
powershell -Command "$content = [System.IO.File]::ReadAllText('%source_dir%\tc.sh').Replace(\"`r`n\", \"`n\"); [System.IO.File]::WriteAllText('%source_dir%\tc.sh', $content, [System.Text.Encoding]::UTF8)"

echo 域名变量更新和格式转换完成！

REM 使用scp将文件夹发送到所有服务器

echo 正在发送文件到 %WORKER1_DOMAIN_NAME%...
scp -r "%source_dir%" %USERNAME%@%WORKER1_DOMAIN_NAME%:%target_dir%

echo 正在发送文件到 %WORKER2_DOMAIN_NAME%...
scp -r "%source_dir%" %USERNAME%@%WORKER2_DOMAIN_NAME%:%target_dir%

echo 正在发送文件到 %WORKER3_DOMAIN_NAME%...
scp -r "%source_dir%" %USERNAME%@%WORKER3_DOMAIN_NAME%:%target_dir%

echo 正在发送文件到 %WORKER4_DOMAIN_NAME%...
scp -r "%source_dir%" %USERNAME%@%WORKER4_DOMAIN_NAME%:%target_dir%

echo 正在发送文件到 %MASTER_DOMAIN_NAME%...
scp -r "%source_dir%" %USERNAME%@%MASTER_DOMAIN_NAME%:%target_dir%

echo 正在发送文件到 %MASTER_DOMAIN_NAME%...
set mubench_dir=D:\adaptation\muBench
REM 创建临时目录用于存放要压缩的文件
set temp_dir=%TEMP%\mubench_temp
mkdir "%temp_dir%" 2>nul

echo 正在复制文件...

REM 复制所有非隐藏文件和文件夹到临时目录
for /f "delims=" %%i in ('dir /b /a-h "%mubench_dir%"') do (
    REM 检查文件名是否以"."开头
    echo %%i
    set "filename=%%i"
    setlocal enabledelayedexpansion
    set "firstChar=!filename:~0,1!"
    if not "!firstChar!"=="." (
        xcopy "%mubench_dir%\%%i" "%temp_dir%\%%i" /E /I /H /Y >nul
    )
    endlocal
)

REM 创建压缩文件名（使用时间戳避免重名）
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (
    set datestamp=%%c%%a%%b
)
for /f "tokens=1-2 delims=: " %%a in ('time /t') do (
    set timestamp=%%a%%b
)
set archive_name=mubench_%datestamp%_%timestamp%.zip

REM 使用PowerShell压缩文件
echo 正在压缩文件...
powershell -Command "Compress-Archive -Path '%temp_dir%\*' -DestinationPath '%temp_dir%\%archive_name%' -Force"

REM 传输压缩文件到目标服务器
echo 正在传输压缩文件到 %MASTER_DOMAIN_NAME%...
scp "%temp_dir%\%archive_name%" %USERNAME%@%MASTER_DOMAIN_NAME%:~/

REM 清理临时文件
rd /s /q "%temp_dir%" 2>nul



REM scp -r "%source_dir%" %USERNAME%@%MASTER_DOMAIN_NAME%:%target_dir%

echo 所有文件传输完成！
