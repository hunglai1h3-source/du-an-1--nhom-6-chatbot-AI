@echo off
setlocal EnableExtensions EnableDelayedExpansion

chcp 65001 >nul
title Cài đặt dự án AI Chatbot

cd /d "%~dp0"

echo ========================================================
echo       HỆ THỐNG CÀI ĐẶT TỰ ĐỘNG - AI CHATBOT
echo ========================================================
echo.
echo Thư mục dự án:
echo %CD%
echo.

:: ==========================================================
:: 1. KIỂM TRA FILE DỰ ÁN
:: ==========================================================

echo [1/7] Đang kiểm tra cấu trúc dự án...

if not exist "app.py" (
    echo [LỖI] Không tìm thấy file app.py.
    echo Hãy đặt setup.bat cùng thư mục với app.py.
    goto :error
)

if not exist "requirements.txt" (
    echo [LỖI] Không tìm thấy file requirements.txt.
    goto :error
)

if not exist ".env.example" (
    echo [CẢNH BÁO] Không tìm thấy file .env.example.
)

echo [OK] Cấu trúc dự án hợp lệ.
echo.

:: ==========================================================
:: 2. TÌM PYTHON
:: ==========================================================

echo [2/7] Đang kiểm tra Python...

set "PYTHON_CMD="

python --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    py --version >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_CMD=py"
    )
)

if not defined PYTHON_CMD (
    echo [LỖI] Không tìm thấy Python trên máy.
    echo.
    echo Hãy cài Python từ:
    echo https://www.python.org/downloads/
    echo.
    echo Khi cài, nhớ chọn:
    echo Add Python to PATH
    goto :error
)

for /f "tokens=*" %%i in ('%PYTHON_CMD% --version 2^>^&1') do (
    echo [OK] Đã tìm thấy %%i
)

echo.

:: ==========================================================
:: 3. KIỂM TRA DUNG LƯỢNG Ổ ĐĨA
:: ==========================================================

echo [3/7] Đang kiểm tra dung lượng ổ đĩa...

for %%D in ("%CD%") do set "PROJECT_DRIVE=%%~dD"

for /f "tokens=3" %%A in (
    'dir /-c "%PROJECT_DRIVE%\" ^| find "bytes free"'
) do (
    set "FREE_BYTES=%%A"
)

if defined FREE_BYTES (
    set /a FREE_MB=!FREE_BYTES!/1024/1024 2>nul

    echo Dung lượng trống ước tính: !FREE_MB! MB

    if !FREE_MB! LSS 1500 (
        echo.
        echo [CẢNH BÁO] Ổ đĩa còn dưới 1.5 GB.
        echo Việc tạo venv và cài thư viện có thể thất bại.
        echo Hãy giải phóng dung lượng trước khi tiếp tục.
        echo.
        set /p CONTINUE_LOW_SPACE="Vẫn tiếp tục? (Y/N): "

        if /i not "!CONTINUE_LOW_SPACE!"=="Y" (
            goto :cancelled
        )
    )
) else (
    echo [CẢNH BÁO] Không thể xác định dung lượng trống.
)

echo.

:: ==========================================================
:: 4. TẠO MÔI TRƯỜNG ẢO
:: ==========================================================

echo [4/7] Đang chuẩn bị môi trường Python...

if exist "venv\Scripts\python.exe" (
    echo [OK] Môi trường venv đã tồn tại.
) else (
    if exist "venv" (
        echo [CẢNH BÁO] Thư mục venv tồn tại nhưng không hợp lệ.
        echo Đang xóa venv lỗi...
        rmdir /s /q "venv"

        if exist "venv" (
            echo [LỖI] Không thể xóa thư mục venv.
            echo Hãy đóng các Terminal đang sử dụng venv rồi thử lại.
            goto :error
        )
    )

    echo Đang tạo môi trường ảo...
    %PYTHON_CMD% -m venv venv

    if errorlevel 1 (
        echo [LỖI] Không thể tạo môi trường ảo.
        echo.
        echo Nguyên nhân có thể:
        echo - Ổ đĩa không đủ dung lượng.
        echo - Python cài đặt bị lỗi.
        echo - Không có quyền ghi vào thư mục.
        goto :error
    )

    echo [OK] Đã tạo môi trường venv.
)

set "VENV_PYTHON=%CD%\venv\Scripts\python.exe"

if not exist "%VENV_PYTHON%" (
    echo [LỖI] Không tìm thấy Python trong venv.
    goto :error
)

echo.

:: ==========================================================
:: 5. TẠO FILE .ENV
:: ==========================================================

echo [5/7] Đang kiểm tra cấu hình môi trường...

if exist ".env" (
    echo [OK] File .env đã tồn tại.
) else (
    if exist ".env.example" (
        copy /y ".env.example" ".env" >nul

        if errorlevel 1 (
            echo [LỖI] Không thể tạo file .env.
            goto :error
        )

        echo [OK] Đã tạo file .env từ .env.example.
        echo [QUAN TRỌNG] Hãy mở .env và điền API key.
    ) else (
        echo [CẢNH BÁO] Không có .env.example nên chưa thể tạo .env.
    )
)

echo.

:: ==========================================================
:: 6. CÀI THƯ VIỆN
:: ==========================================================

echo [6/7] Đang cài đặt thư viện...
echo Quá trình này có thể mất vài phút.
echo.

"%VENV_PYTHON%" -m pip --version >nul 2>&1

if errorlevel 1 (
    echo Đang cài pip vào môi trường ảo...
    "%VENV_PYTHON%" -m ensurepip --upgrade

    if errorlevel 1 (
        echo [LỖI] Không thể cài pip.
        goto :error
    )
)

"%VENV_PYTHON%" -m pip install -r requirements.txt

if errorlevel 1 (
    echo.
    echo [LỖI] Không thể cài đầy đủ thư viện.
    echo.
    echo Hãy kiểm tra:
    echo - Kết nối Internet.
    echo - Dung lượng ổ đĩa.
    echo - Phiên bản Python.
    echo - Nội dung requirements.txt.
    goto :error
)

echo.
echo [OK] Đã cài đặt thư viện thành công.
echo.

:: ==========================================================
:: 7. HOÀN TẤT
:: ==========================================================

echo [7/7] Cài đặt hoàn tất.
echo ========================================================
echo.
echo Lệnh chạy ứng dụng:
echo "%VENV_PYTHON%" app.py
echo.

set /p CHOICE="Bạn có muốn chạy Chatbot ngay bây giờ không? (Y/N): "

if /i "%CHOICE%"=="Y" (
    echo.
    echo Đang khởi động ứng dụng...
    echo Địa chỉ: http://127.0.0.1:5000
    echo Nhấn Ctrl + C để dừng máy chủ.
    echo.

    "%VENV_PYTHON%" app.py

    if errorlevel 1 (
        echo.
        echo [LỖI] Ứng dụng đã dừng do có lỗi.
        echo Hãy đọc thông báo lỗi phía trên.
        goto :error
    )
) else (
    echo.
    echo Cài đặt đã xong.
    echo Khi cần chạy lại, hãy mở Terminal tại thư mục dự án và dùng:
    echo.
    echo venv\Scripts\python.exe app.py
)

echo.
pause
exit /b 0

:error
echo.
echo ========================================================
echo CÀI ĐẶT KHÔNG HOÀN TẤT
echo ========================================================
echo.
pause
exit /b 1

:cancelled
echo.
echo Đã hủy cài đặt.
pause
exit /b 0