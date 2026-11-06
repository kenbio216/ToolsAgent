# 山野装备助手 · ToolsAgent

[打开装备助手](https://kenbio216.github.io/ToolsAgent/)

React + Tailwind 三步装备登记：核对个人装备、核对本人携带的集体装备、装备登记与交流。第三步支持借出、归还、照片、语音文字和集体补报；同名最新确认更新当前数量，每次前后流水保留。确认前的计划数量仅为草稿。

## 部署边界

GitHub Pages 仅发布 `frontend/dist`，不运行模型或保存借还记录。AI、Whisper语音和飞书同步继续在本机运行，通过独立HTTPS入口连接。管理页面不发布到Pages，不由公开接口转发，继续沿用本人私有入口。

本次后端入口采用免账号 Cloudflare Quick Tunnel：本机和后台服务必须在线；它没有可用性保证，进程重启会换地址。本机维护器会更新 `frontend/public/api-config.json` 并触发Pages重新发布。长期使用应迁移到有固定域名的正式后端；不要将临时入口视为托管服务器。

## 开发

需要 Node.js 24。`cd frontend && npm ci && npm run dev`。默认使用同域 `/api/gateway/equipment-agent`。Pages构建设置 `VITE_BASE_PATH=/ToolsAgent/`、`VITE_EQUIPMENT_REMOTE=1`，从公开配置文件读取独立HTTPS后端。

后端源码在 `backend/`。实际名单、飞书token和URL由本机配置提供；复制 `roster.example.json` 为不入库的 `roster.local.json`，设置 `EQUIPMENT_ROSTER_FILE`、`EQUIPMENT_FEISHU_TOKEN`、`EQUIPMENT_FEISHU_URL`。`agent_model.py`通过已配置的Hermes读取GLM接口，不包含密钥。语音服务需要另行配置本地Whisper。

IP归属地使用离线ip2region，结果是网络归属地估计，不是实时位置。运行 `python3 scripts/download_geo.py` 下载固定版本数据。本项目保留第三方Apache-2.0许可。

## 数据与发布

公开仓库包含通用源码和示例计划，不含实际名单、对话、照片、借还历史、访问IP、私有管理数据、Hermes配置或API密钥。GitHub Actions只上传前端构建产物。IP库文件也不上传Pages。
