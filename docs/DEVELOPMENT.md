# 组内修改与复现

先按根目录 README 完成一次检查。所有命令在仓库根目录执行。

```powershell
runtime\python\python.exe scripts\verify_project.py
runtime\python\python.exe scripts\verify_project.py --recompute M2 encounter_M1_opposing
runtime\python\python.exe build_anylogic_visual.py --jar-only
```

最后一条仅在修改 Java 展示源码后需要。先关闭**本目录**的仿真模型释放 JAR，再用已安装 AnyLogic 自带的 javac/jar 编译；编译输出不提交。此脚本只重建当前展示 JAR，保留当前模型 XML；修改模型请针对 `anylogic/AIS_Visual_Demo.alp` 的当前模板进行。

`runtime/python/python311._pth` 将导入路径限定为本地运行库和本项目根目录，不需要激活虚拟环境。依赖版本列在 runtime/packages/windows-python.manifest.json，开发者应同步维护离线运行库而不是要求组员全局 pip install。scripts/release/build_python_runtime.py 的命令行帮助提供维护者重建入口。

原始输入和已验收结果在 runtime/data/current-data.zip 中无损保存，manifest 列出每个原件的字节数和 SHA256。为适应 GitHub 大文件限制使用 ZIP，不改写原 JSON，不使用 Git LFS 指针。自动准备不会覆盖已改动的原始输入；研究修改请先留存原件并明确更新版本和证据。

`data/`、`output/`、`.local/` 和运行库解压目录均被忽略；组员运行产生的新结果需要主动选择、审查后单独归档提交。历史报告中的本机绝对路径仅用于追溯当时运行，不是当前启动依赖。真实 API 密钥不得提交。

`.gitattributes` 禁止自动转换文件换行，确保 Git 下载得到的配置、来源和源码字节与原哈希一致；修改文件时也应保留其编码与换行。
