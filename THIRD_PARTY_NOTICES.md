# 第三方来源与分发范围

- Python 3.11.9 使用官方 Windows embedded x64 原件。来源：https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip 。原始许可证随 runtime/packages 的运行库归档保留。
- Python 包版本及压缩包/分片 SHA256 见 runtime/packages/windows-python.manifest.json。各发行包原有 dist-info 许可证、NumPy/Shapely/pyproj 等依赖库许可及 Playwright driver 所附第三方声明均保留在归档内。
- OMPL 2.0.2 固定 commit、原 SST 搜索及适配源码哈希见 runtime/ompl/manifest.json；OMPL-LICENSE 和 DLL runtime-licenses 目录一并保留。适配源码为 sst_probe.cpp。
- AnyLogic 未打包或重新分发。组员须自行从官方安装并使用适用的许可证。本项目借用已安装 AnyLogic 的 Java、引擎、Gson 和 Chromium。
- 官方建筑/渡轮/航道的来源清单及原件在离线数据包内；首启还原后见 data/official/snapshots/28991d3a0c66d1fa/source_manifest.json。AIS 唯一船位来源为 AISStream 的既有历史采集，不包含 API Key。岸线/植被/填海原件与加工记录见 docs/provenance/scenery。
- 原仓库未为原创项目代码另行声明开源许可证。本次整理保留原权属和第三方许可，不擅自为所有代码添加 MIT 等新许可证。
