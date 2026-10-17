# 双平台稳定更新计划

用户已确认增加 Windows，以完整沿用现有应用内更新体验。本计划取代初版 Android-only 预发布策略。

- 固定同一个已审查 source SHA、同一输入版本，在独立 Linux/Windows runner 构建真实 APK 和 Inno Setup 安装包。
- 保留原 Windows build_windows.bat、emosonic.iss、升级 GUID、安装目录、用户级安装模式与运行文件名。临时构建副本只替换 pubspec 版本，结束后恢复，不向源码仓库提交。
- Android 原证书校验不变。Windows 校验原脚本/模板摘要、安装器 AppId/安装范围、内含 emosonic.exe 的 PE x64 架构和数字/字符串版本，并仅解包、不运行安装包。
- 新增 windows-build 环境（SOURCE_READ_TOKEN、DEFAULT_SERVER_URL）；保留 android-build、android-release 名称，发布环境负责两个平台。
- 独立无用户 Secrets 的验证 job 分别验证两平台；最后的发布 job 只核验哈希与脱敏来源数据，不执行产品二进制或私有源码。
- 只在所有构建/验证成功后创建 vX.Y.Z+N 草稿，上传两包、两份校验和、两份脱敏 manifest，再核对全部远端摘要，转换成正式 latest。缺平台、来源/版本不匹配、已存在标签或版本回退均拒绝。
- 不复用旧 Windows 安装包，不覆盖已发布资产，不修改产品更新器或旧 workflow。
- 增加双平台缺失、版本/来源错配、旧客户端标签契约、上传失败保持草稿等测试；检查 Actions 语法并以合成安装包验证 Windows 检验器。
- 本次不运行真实源码编译/发布，仍等待用户自行配置 Secrets 并确认版本。
