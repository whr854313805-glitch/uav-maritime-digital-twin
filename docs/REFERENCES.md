# 本次打包实现依据

本次只整理启动、依赖、文件布局和验证，不改规划算法。

- Python 官方 Windows embedded distribution：https://docs.python.org/3.11/using/windows.html#the-embeddable-package 。采用应用随附运行库及固定第三方依赖，避免复制开发 venv。
- AnyLogic 官方命令行运行模型：https://anylogic.help/anylogic/running/export-java-application.html 。使用已安装 AnyLogic 的 `-r <ALP> Simulation`；本项目没有将 PLE 模型冒称为已获许可的独立导出应用。
- 文件归档、逐文件 SHA256、相对路径、原子临时文件替换属于本次工程实现。解压后必须与原始数据 manifest 一致，不是新实验方法或新数据来源。
- 当前源文件/参数/算法来源沿用 F20、F21、F23 的原始证据与本仓库 runtime/ompl/manifest.json；没有新增个人开发经历或历史来源声明。
