# 图片查看与裁剪工具

本程序是一个简单的Windows桌面应用，允许用户查看图片，并通过鼠标滚轮缩放、拖动以及保存当前可见区域。

## 功能

*   **打开图片**: 支持常见的图片格式 (PNG, JPEG, GIF, BMP)。图片打开时会自动调整大小以适应窗口。
*   **缩放图片**: 使用鼠标滚轮进行放大和缩小。
*   **拖动图片**: 当图片放大后，可以按住鼠标左键拖动图片。
*   **保存裁剪区域**: 按下 `Ctrl+S` 快捷键，程序将直接把当前窗口中可见的图片部分以新的文件名（包含时间戳）保存在原图片所在的文件夹中，不再弹出保存对话框。

## 环境要求

*   Python 3

## 安装依赖

本程序主要依赖 Pillow 库来处理图片。同时，为了支持更高级的图像处理功能和可选的GPU加速，还引入了 OpenCV 库。

*   **Pillow**: 用于基本的图像操作。
    ```bash
    pip install Pillow
    ```
*   **OpenCV**: 用于图像处理，特别是图像缩放，并支持通过CUDA进行GPU加速。
    ```bash
    pip install opencv-python
    ```

## GPU 加速 (可选, 适用于NVIDIA显卡)

如果您的计算机配备了兼容的NVIDIA显卡并正确配置了CUDA环境，本程序可以利用GPU进行图像缩放操作（例如，生成预览图和实时显示时的缩放），从而显著提升处理性能，尤其是在处理大尺寸图片或进行频繁缩放操作时。

**系统要求**:

*   一块支持CUDA的NVIDIA显卡。
*   已正确安装并配置NVIDIA CUDA Toolkit。
*   安装了支持CUDA的OpenCV版本。
    *   标准的 `opencv-python` 包通常**不包含**CUDA支持。
    *   您可能需要安装特定的预编译包（例如，某些平台和Python版本下的 `opencv-python-headless` 可能包含CUDA支持）或者从源码编译OpenCV并启用相关的CUDA编译选项。

**工作方式**:

程序启动时会自动检测系统中是否存在支持CUDA的OpenCV版本和NVIDIA显卡。如果检测成功，程序将自动启用GPU加速功能。否则，程序将平稳回退到使用CPU进行图像处理。

您可以在程序启动时查看控制台（命令行界面）的输出信息，以确认OpenCV库是否加载成功以及GPU加速是否可用。相关信息示例：
*   `OpenCV library found.` / `OpenCV library not found.` (OpenCV库已找到 / 未找到)
*   `GPU acceleration is available.` (GPU加速可用)
*   `GPU acceleration not available (no CUDA devices found).` (GPU加速不可用 - 未找到CUDA设备)
*   `GPU acceleration not available (OpenCV not compiled with CUDA support).` (GPU加速不可用 - OpenCV未编译CUDA支持)

## 如何运行

1.  确保您已安装 Python 3 和 Pillow 库。
2.  下载或克隆本仓库中的 `image_viewer.py` 和 `test_image_viewer.py` (测试文件可选) 文件。
3.  打开命令行工具 (如 Command Prompt 或 PowerShell)。
4.  导航到 `image_viewer.py` 文件所在的目录。
5.  运行以下命令启动程序：

```bash
python image_viewer.py
```

程序窗口将会打开，您可以通过 "文件" -> "打开..." 菜单来选择图片。
