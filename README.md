# 山野装备助手 · ToolsAgent

[打开装备助手](https://kenbio216.github.io/ToolsAgent/)

React + Tailwind 三步装备登记：核对个人装备、核对本人携带的集体装备、装备登记与交流。第三步支持借出、归还、照片、语音文字和集体补报；同名最新确认更新当前数量，每次前后流水保留。确认前的计划数量仅为草稿。

借出确认后会按已确认的自备、借用和实际携带记录补问头灯、救生毯、雨衣、对讲机；补问和借还快捷按钮采用固定引导，不额外调用模型。必备装备的自备数量与“暂不补登记/尚未准备”说明仍需本人确认，后者不代表已经带齐。

## 部署边界

GitHub Pages 仅发布 `frontend/dist`，不运行模型或保存借还记录。AI、Whisper语音和飞书同步继续在本机运行，通过独立HTTPS入口连接。管理页面不发布到Pages，不由公开接口转发，继续沿用本人私有入口。

本次后端入口采用免账号 Cloudflare Quick Tunnel：本机和后台服务必须在线；它没有可用性保证，连接进程重启会换地址。维护器和连接进程已分离，维护器重启会复用健康连接；更换连接时先验证新入口再发布。本机维护器会更新 `frontend/public/api-config.json` 并触发Pages重新发布。长期使用应迁移到有固定域名的正式后端；不要将临时入口视为托管服务器。

## 开发

需要 Node.js 24。`cd frontend && npm ci && npm run dev`。默认使用同域 `/api/gateway/equipment-agent`。Pages构建设置 `VITE_BASE_PATH=/ToolsAgent/`、`VITE_EQUIPMENT_REMOTE=1`，从公开配置文件读取独立HTTPS后端。

后端源码在 `backend/`。实际名单、飞书token和URL由本机配置提供；复制 `roster.example.json` 为不入库的 `roster.local.json`，设置 `EQUIPMENT_ROSTER_FILE`、`EQUIPMENT_FEISHU_TOKEN`、`EQUIPMENT_FEISHU_URL`。`agent_model.py`通过已配置的Hermes读取GLM接口，不包含密钥。语音服务需要另行配置本地Whisper。

IP归属地使用离线ip2region，结果是网络归属地估计，不是实时位置。运行 `python3 scripts/download_geo.py` 下载固定版本数据。本项目保留第三方Apache-2.0许可。

## 数据与发布

公开仓库包含通用源码和示例计划，不含实际名单、对话、照片、借还历史、访问IP、私有管理数据、Hermes配置或API密钥。GitHub Actions只上传前端构建产物。IP库文件也不上传Pages。

## 安全与限制

姓名是自行填写的登记标识，不是经过验证的身份。知道其他人姓名的人可能影响该姓名下的共享装备数量；修改流水用于追查，不能替代身份核验。当前没有协会账号导入。

公开桥仅允许成员接口，强制非管理员身份，屏蔽私人飞书链接，并限制请求体、并发和调用频率。CORS网页来源校验不是身份认证，非浏览器客户端可伪造Origin。全站模型请求默认每小时120次、每天300次，内存计数重启会清零，不能代替服务商费用上限。

访问设备、IP和使用记录仅负责人在私有管理页查阅；IP位置在本机离线估计。GitHub及HTTPS代理服务会处理网络请求，模型服务会接收文字和照片，本地语音先转成文字。
