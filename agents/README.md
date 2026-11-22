# Healthcare Agents

独立的实时 NABH 认证验证 Agent。输入医疗机构的名称和地址，实时查询 NABH 官方目录、
读取目录链接的认证 PDF，由火山方舟模型核对机构与分院，并返回带原文证据的 JSON。

本目录属于 `cmu-datathon-virtue-healthcare` 仓库，包含 NABH 验证和医疗需求意图解析两个命令行应用。
不依赖 Databricks、Lakehouse 或 Lakebase。

## 快速启动 Demo

需要 Python 3.10+。**本 README 下方命令默认在仓库的 `agents/` 目录执行**，
不是仓库根目录，也不需要克隆独立的 NABH-check 仓库。

从当前仓库根目录开始：

```bash
cd agents
python3 --version  # 必须为 3.10 或更高版本
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest -v test_verify test_intent_agent test_specialities
python verify.py --help
python intent_agent.py --help
```

macOS 的 `/usr/bin/python3` 可能是 3.9。若版本不足，用已安装的新版解释器创建环境，
例如本机可用的 `~/miniconda3/bin/python3 -m venv .venv`，之后同样激活并安装依赖。
已经用旧版 Python 创建过环境时，可用新版解释器创建 `.venv310`，并激活该目录。
Windows PowerShell 激活命令为 `.venv\Scripts\Activate.ps1`。

每次打开新终端，先进入 `agents/` 并执行 `source .venv/bin/activate`。
用 `python -m pip` 可以确保依赖安装到当前解释器；`verify.py` 需要 BeautifulSoup、pypdf 等依赖，
`test_intent_agent.py` 是离线单元测试，不是调用模型的应用入口。
测试不需要 API Key，也不会调用官网或模型。

也可以留在**仓库根目录**，直接使用虚拟环境解释器，无需激活：

```bash
agents/.venv/bin/python agents/verify.py --help
agents/.venv/bin/python agents/intent_agent.py --help
agents/.venv/bin/python -m unittest discover -s agents -p 'test_*.py' -v
```

### 两个 Agent 共用的配置

`verify.py` 和 `intent_agent.py`（包括对应的 Python 函数入口）都默认读取
**脚本目录中的 `agents/.env`**，不受启动时工作目录影响，不自动读取仓库根目录 `.env`。

```bash
# 在 agents/ 目录执行；仅首次创建，已有 .env 时不要覆盖
cp -n .env.example .env
```

编辑 `.env`，填入真实配置：

```dotenv
ARK_API_KEY=你的真实APIKey
ARK_MODEL=账号中已开通的模型或endpointID
```

两个脚本都支持 `--env-file /path/to/custom.env`，Python 函数都支持 `env_file=Path(...)`。
加载规则相同：文件值覆盖同名终端环境变量；默认 `.env` 不存在时仅使用终端环境变量；
指定的其他文件不存在、格式错误或不可读时返回配置错误。
支持 `KEY=VALUE`、`export KEY=VALUE`、引号和 `#` 注释，不执行 shell 命令或变量展开。
配置文件须使用 UTF-8 编码；`.env` 和虚拟环境已被 Git 忽略，`.env.example` 只含占位符。
无需模型的 `--directory-only` 不要求 Key；其他实际模型调用需要有效 Key 和模型权限。

### Demo 1：无需 API Key 的官网实时查询

```bash
python verify.py \
  --name 'Accord Hospital' \
  --address 'Sant Nagar, Sector No.4, Plot No.1/1, Moshi Pradhikaran, Pune, Maharashtra 412105' \
  --directory-only
```

输出候选机构的名称、地址、认证号、官方状态和 `pdf_url`。
`status: not_attempted` 表示只查询官网，尚未执行 PDF 与模型验证。
这是源站连通性 Demo，不是模拟数据，也不会产生模型调用。

### Demo 2：火山方舟完整 Agent 验证

在火山方舟控制台创建 API Key，并开通支持 Responses API 的模型或推理接入点。
按上文配置 `.env`，或在未创建 `.env` 时设置终端环境变量：

```bash
export ARK_API_KEY='你的真实 API Key'
export ARK_MODEL='已开通的模型 ID 或 endpoint ID'

python verify.py \
  --name 'Accord Hospital' \
  --address 'Sant Nagar, Sector No.4, Plot No.1/1, Moshi Pradhikaran, Pune, Maharashtra 412105'
```

两个脚本自动加载 `agents/.env`；使用其他配置时添加 `--env-file /path/to/custom.env`。
Key 只留在本地/后端环境。完整验证会把机构名称、地址和证书文本发送给火山方舟。
不需要开通联网搜索组件：Python 实时读取官网和 PDF，方舟模型只分析本次获取的证据。

保存结果：

```bash
python verify.py \
  --name 'Accord Hospital' \
  --address 'Sant Nagar, Moshi Pradhikaran, Pune, Maharashtra 412105' \
  > /tmp/nabh-result.json
```

可将输入地址换为 `Mumbai, Maharashtra 400001`，观察分院地址/邮编冲突的处理。
结果由实时官网记录和模型输出决定，不保证示例每次均为 `verified`。
一次完整验证会执行多次网络请求，可能需要数分钟。

### 方舟响应超时排查

默认使用 `thinking: disabled`、`max_output_tokens: 4096`，方舟 socket 超时为 180 秒。
这适用于 `doubao-seed-2-1-pro-260915` 的证据提取 Demo；原先未设置 thinking 的请求
可能启用深度思考，延长等待时间。网络延迟、服务排队也可能导致超时。
此超时是网络 socket 等待时间，不是整个任务的总时限。

```bash
export ARK_MODEL='doubao-seed-2-1-pro-260915'
export ARK_THINKING=disabled
export ARK_TIMEOUT_SECONDS=180
export ARK_MAX_OUTPUT_TOKENS=4096

python verify.py \
  --name 'Accord Hospital' \
  --address 'Sant Nagar, Sector No.4, Plot No.1/1, Moshi Pradhikaran, Pune, Maharashtra 412105' \
  --verbose
```

`--verbose` 将阶段日志写到 stderr，不影响 stdout 的 JSON。
若仍超时，可将 `ARK_TIMEOUT_SECONDS` 提高到 300（最大 600），并检查运行环境到
`ark.cn-beijing.volces.com` 的网络连接。脚本不自动重试模型请求，避免重复发起收费调用。
若返回 HTTP 401/403/404，应检查 Key、模型访问权限和模型 ID，而不是继续增大超时。
需要深度思考时可设 `ARK_THINKING=enabled`，并相应增加超时和输出 token 预算。

## 验证流程

```text
名称 + 地址
    ↓
NABH 官网 AJAX 查询
    ↓
提取候选机构、地址、认证号、状态和证书链接
    ↓
实时下载 PDF → 提取文本 → 计算 SHA-256
    ↓
火山方舟：核对同一分院，提供名称、地址、证书号、有效期原文
    ↓
代码：检查引用、邮编冲突、证书号、认证类型和有效期
    ↓
JSON 结果 + 证据 + PDF URL
```

官网当前使用 `POST https://nabh.co/wp-admin/admin-ajax.php`，主要表单字段为
`action=get_hospitals`、`q=<机构名称>` 和 `page=1`。
这是官网前端使用的 AJAX 接口，未发现具有稳定性承诺的公开 REST API 文档。

脚本最多查询 2 页、处理前 4 个候选。达到限制时保留待审核，不自动通过。
只接受允许名单中的来源主机，包括官网实际链接的一个具体 S3 证书桶；
检查重定向、PDF 签名、体积，并拒绝未知下载主机。
官网请求失败、验证码、响应结构变化不会被判为“没有认证”。

参考：
- [NABH 官方机构查询](https://nabh.co/find-a-healthcare-organisation/)
- [官网查询 JavaScript](https://nabh.co/wp-content/themes/nabh/js/my-map.js)
- [火山方舟 Responses API](https://docs.volcengine.com/docs/ark/create-model-responses-api?lang=zh)

## 输出

| 字段 | 含义 |
| --- | --- |
| `facility` | 输入的名称和地址 |
| `checked_at` / `as_of_date` | 本次抓取时间与有效期判断日期，UTC |
| `status` | 整体验证结果 |
| `certificate_urls` | 整体验证成功时的 PDF 链接 |
| `candidates[]` | 候选名称、地址、认证号、官网状态、PDF 链接 |
| `candidates[].pdf` | PDF 哈希、最终响应 URL 或下载错误 |
| `candidates[].verification` | 匹配结论、日期判断、模型理由与原文引用 |
| `warnings` | 候选截断等限制 |

| status | 含义 |
| --- | --- |
| `verified` | 分院匹配、证据齐备、目录表明已认证且证书在有效期内 |
| `expired` / `not_yet_valid` | 当前日期不在证书有效期内 |
| `listed_only` | 有目录记录，但不能据此认定 active accreditation，例如 Empaneled |
| `needs_review` | 身份不确定、证据不足、PDF 不可读或候选被截断 |
| `no_match` | 本次名称搜索没有结果，不代表没有认证 |
| `source_unavailable` | 官方查询失败或响应结构变化 |
| `agent_error` | 方舟调用失败或响应不合规 |
| `configuration_error` | 未设置 `ARK_API_KEY` 或 `ARK_MODEL` |
| `not_attempted` | 仅运行了 `--directory-only` |

## 在自己的后端调用

在仓库根目录中可按下面方式导入；若已进入 `agents/`，则使用 `from verify import verify_facility`。在工作线程/任务队列中调用：

```python
from agents.verify import verify_facility

result = verify_facility(
    name="Accord Hospital",
    address="Sant Nagar, Moshi Pradhikaran, Pune, Maharashtra 412105",
)
```

这是同步网络任务，不应直接阻塞异步服务的事件循环。
Node.js 后端亦可使用 `execFile` 启动 CLI，并通过参数数组传入名称和地址；不要拼接 shell 命令。

## 测试

```bash
python -m unittest -v test_verify test_intent_agent test_specialities
```

离线测试覆盖有效期、分院邮编冲突、Empaneled 与认证的区别、虚构引用、证书号不一致、
扫描 PDF、下载域名限制、源站失败和候选截断。
以上为离线测试；真实官网查询使用 `--directory-only`，火山方舟完整链路需要配置有效 Key 后运行。

## 限制

`verified` 只表示本次证据支持该分院的机构认证，不代表所有服务、医生或床位实时可用。
当前不逐项验证服务范围，不对扫描件做 OCR。没有缓存，每次重新查询，PDF 不落盘。
名称搜索可能因拼写或旧名称漏召回；分院语义匹配及日期标签理解仍依赖模型。
引用检查不是证书数字签名验证，也不能发现官网尚未更新的撤销信息。

## Specialities 归类与映射

输入为 `raw_specialties.json`，输出与源文件一致使用 UTF-8 JSON 数组。
运行以下命令可以重新生成两张表，仅使用 Python 标准库，无模型或网络调用：

```bash
python3 summarize_specialities.py
python3 -m unittest -v test_specialities
```

也可指定输入和输出目录：

```bash
python3 summarize_specialities.py --input raw_specialties.json --output-dir ./output
```

当前数据的结果：

| 项目 | 数量 |
| --- | ---: |
| 原始不同条目 | 2,695 |
| `specialities_summarize.json` 分类行数 | 118 |
| `specialities_mapping.json` 映射行数 | 2,955 |
| 涉及多个分类的原始条目 | 256 |
| 待复核原始条目 | 47 |
| Agent 分类表行数减少比例 | 95.62% |

118 行包含 116 个可路由类别，以及 `SP_UNSPECIFIED`、`SP_UNRESOLVED` 两个特殊类别。
行数减少比例不等于 token 减少比例，也不代表分类准确率。当前结果是规则生成的本地服务分类，
没有经过独立临床专家逐项校验，也没有对齐到官方 NABH、SNOMED CT 或 UMLS 编码。

### 方法与粒度

采用“规则式 NLP 标准化 → 专科/服务词典 → 特例修正 → 多分类映射 → 完整性检查”。
针对这份规模固定、英文短词占多数的列表，该方案可复现、可解释，便于增量维护。
文本预处理包括 Unicode 规范化、CamelCase 分词、大小写、标点和英美拼写统一，
以及观察到的常见拼写错误修正。保留原始文本，不排序或删除有临床意义的词。

词典按服务范围归类，而非把所有医学上相关的词当成同义词。
例如麻醉的多种写法归为同组；心脏内科、介入心脏病学、心脏外科分开，
眼科进一步区分白内障、青光眼、视网膜、屈光手术等，牙科也按子领域拆分。
`CARDIOLOGY & ENT` 同时归到两个类别，`Anaesthesia & Critical Care` 同理。
儿科等年龄信息通过 `age_scope` 保留，避免仅凭年龄丢失器官专科。

这是面向 Agent 检索和路由的分类粒度。归到同组不代表同一种检查或手术，
例如不同实体器官的移植在本轮归为一组，仍需通过原文识别具体器官。
Agent 选择类别后可以取回组内候选；精确服务匹配应进一步使用原文和年龄等约束。

没有仅凭向量相似度自动聚类：相同器官的内科、外科、检查、麻醉可能很相近，
业务上却需要保留边界。将来遇到新条目，可用医学文本 embedding 提名候选，再核查并加入词典；
当前脚本不依赖 embedding，也没有发起付费模型调用。

方法参考 [NLM 的词汇规范化说明](https://www.nlm.nih.gov/research/umls/new_users/online_learning/LEX_005.html)
和 [SNOMED CT 映射规则](https://docs.snomed.org/snomed-ct-practical-guides/snomed-ct-mapping-guide/developing-use-case-and-requirements/5.3.2-mapping-rules)。
这里参考其规范化和保留映射方向的原则；没有实际调用这些术语库。

### 两份文件的字段

`specialities_summarize.json` 供 Agent 读取：

| 字段 | 含义 |
| --- | --- |
| `speciality_id` | 稳定分类 ID，例如 `SP_CARDIOLOGY` |
| `speciality_name` / `speciality_name_zh` | 英文名 / 中文名 |
| `scope` | 类别覆盖的服务范围 |
| `source_entry_count` | 归入此类的不同原始条目数量 |
| `needs_review_count` | 此类中待复核的原始条目数量 |
| `examples` | 最多四个原文示例，不是完整的组内成员列表 |
| `routable` | 是否可作为路由类别；两个特殊类别为 false |
| `taxonomy_version` | 归类规则版本 |

`specialities_mapping.json` 保留可供后续关联的完整映射：

| 字段 | 含义 |
| --- | --- |
| `source_id` | 原文 SHA-256 的前 16 个十六进制字符，加 `SRC_` 前缀 |
| `raw_speciality` | 完整保留的原始条目，精确关联优先使用此字段 |
| `normalized_speciality` / `normalized_key` | 标准化文本 / 去空格后的查找键 |
| `speciality_id` | 关联到汇总表的分类 ID |
| `mapping_relation` | `routing_membership` 为范围归属；`equivalent_label` 仅表示与类别名称标准化后相同；`unresolved` 为未解析 |
| `mapping_method` | 词汇规则、显式特例或未命中规则 |
| `age_scope` | 原文明确提及的年龄范围；未提及为 `unspecified` |
| `is_multi_category` | 同一原始条目是否有多个目标类别 |
| `needs_review` / `review_reason` | 待复核标记和原因 |
| `rule_id` / `taxonomy_version` | 对应脚本中的规则与版本 |

每行是一对“原始条目—分类 ID”，组合键为 `(source_id, speciality_id)`。
原文可能重复出现在多个映射行，因此汇总计数相加得到 2,955，而不是 2,695。
`normalized_key` 不是主键：不同原文可能规范化成同一个键。
脚本检查当前数据中同一标准化键的分类一致性，但未来新增数据仍需重新检查。
ID 不随输入排序变化；修改原文会生成新的 `source_id`，修改类别含义时应调整规则版本。

### Agent 使用方式与复核

让 Agent 读取汇总表的 ID、名称、范围和示例，返回 `speciality_id`。
后续系统按这个 ID 从映射表展开原始条目即可；本项目只输出数据文件，不实现数据库导入或查询。
自动路由时跳过 `routable=false` 的分类，并排除 `needs_review=true` 的映射。
遇到需要精确服务或年龄的请求，继续筛选原文和 `age_scope`；`unspecified` 不代表成人，也不能据此确定儿科服务。

47 个待复核条目包括 36 个含义不足/异常的条目、7 个未指明的综合类别、
3 个未说明细胞类型的干细胞移植名称，以及一个把 JSON 对象存成字符串的条目。
例如 `implant`、`PRP`、`Stones` 不自动猜测身体部位；
`{"dentistry":"dentistry"}` 可识别为牙科，但保留原文并标记格式异常。
未命中规则的新条目进入 `SP_UNRESOLVED`，不自动套用文本最相近的类别。

九项离线回归检查覆盖全量来源完整性、组合键唯一性、分类引用、确定性重建、
标准化键一致性、专科边界、复合条目和易混淆字串。
例如防止把 `neurology` 误归到 `urology`，或把腹腔镜泌尿手术中的字串误识别为 PICU。
这些检查验证数据结构和已知边界，不提供临床分类准确率估计。

## 医疗需求意图解析 Agent

`intent_agent.py` 是独立的英文意图解析应用，可通过命令行或 Python 函数调用。
它使用火山方舟模型读取用户请求和汇总表，选择一个最适合主要医疗需求的分类 ID，
再由 Python 从映射表取出该 ID 下的全部原始 specialties。模型不会读取完整映射表。
独立脚本只输出意图 JSON；整个应用通过 `app/api.py` 自动将这个输出传给医院查询和 PostgreSQL 评分，
详见 [完整应用启动说明](../app/README.md#run-the-complete-query-workflow)。意图解析本身不执行认证验证或数据库查询。

### 运行

与 `verify.py` 一致，默认自动读取 `agents/.env` 中的 `ARK_API_KEY` 和 `ARK_MODEL`。
文件中的配置优先于终端环境变量；不再使用 `ARK_INTENT_MODEL`。
应用不会修改 `.env` 中的模型 ID 或 API Key。

```bash
python3 intent_agent.py \
  --text 'Which hospital near Lucknow can handle an emergency C-section?'
```

也可以通过 `--env-file` 指定其他配置文件：

```bash
python3 intent_agent.py --env-file /path/to/custom.env \
  --text 'Where can I get dialysis in Lucknow, PIN code 226010?'
```

`ARK_MODEL` 应填写账号中已开通的 Responses 模型/接入点 ID。
如果模型返回 404，应检查 `.env` 中的模型 ID 与账号权限；应用不会自动换用其他模型。
`agents/.env` 不存在时，使用进程环境中的 `ARK_MODEL` 和 `ARK_API_KEY`。

省略 `--text` 时从标准输入读取请求，方便管道调用。添加 `--verbose` 可将简要调用日志写到 stderr，
stdout 保持为一个 JSON 对象。成功退出码为 0；请求需要补充信息、配置不正确或模型调用失败时为 1。

### 输出约定

成功输出恰好包含四个顶层字段：

| 字段 | 类型与规则 |
| --- | --- |
| `location.postcode` | 字符串或 JSON `null`；仅从用户明确给出的邮编提取，保留前导零；不根据城市推测 |
| `location.city` | 字符串或 JSON `null`；从请求中明确提到的城市提取；不根据邮编推测 |
| `specialities` | 字符串数组；选定分类 ID 下的全部原始条目 |
| `range` | 正数，查询距离半径，单位 km；未指定距离时默认 `30`，支持小数，例如 `5`、`12.5` |
| `service` | 1–3 个简短英文服务名称组成的数组，例如 `["dialysis"]` 或 `["emergency C-section"]` |

`specialities` 和 `service` 使用数组，以容纳多个值。`null` 是 JSON 空值，不是字符串 `"null"`。
分类 ID 是内部决策字段，不额外加入用户要求的输出结构。

例如，用户的紧急剖宫产请求会选择 `SP_OBGYN`，返回 `city: "Lucknow"`、`postcode: null`、
`service: ["emergency C-section"]`，以及此 ID 下完整的妇产科条目数组。
这个类别由主要医疗服务决定，不能仅因出现 “emergency” 就选择通用急诊类别。
未指定距离时同时返回 `"range": 30`。例如请求
`Find dialysis within 5 km of Lucknow` 时返回 `"range": 5`；明确指定英里时换算为 km。
`range` 必须是有限正数，不接受字符串、布尔值、零或负数。后续 API 和命令行查询
使用它筛选距离范围，API 通过 `radiusKm` 将实际查询半径返回前端。

按本次“返回 ID 下全部条目”的要求，Agent 的 `specialities` 数组保留映射表中该 ID 的所有原文，
包括其待复核条目，不自动删减，也不额外筛选某项手术或年龄。
服务描述是需求提取结果，不表示返回列表中的每个条目都能独立完成该项服务。
它也不表示任何医院确实具备该服务能力。

如果城市和邮编都缺失，例如 `I need dialysis near me.`，应用不会生成缺少地点的成功结果，
而会返回可供前端追问的错误对象：

```json
{
  "error": {
    "code": "location_required",
    "message": "A city or explicit postcode is required.",
    "clarification_question": "Which city or postcode should I search in?"
  }
}
```

多个候选地点或多个无明确优先级的医疗需求会返回 `clarification_required`。
其他错误包括 `invalid_input`、`speciality_required`、`configuration_error`、`catalog_error`、
`model_error` 和 `invalid_model_output`。错误输出与成功的四字段结构分开。

### Python 调用与配置

以下导入适用于仓库根目录；在 `agents/` 内使用 `from intent_agent import ...`。

```python
from agents.intent_agent import IntentError, SpecialityCatalog, parse_intent

catalog = SpecialityCatalog()  # 后端可在启动时加载一次，在多次请求之间复用
try:
    result = parse_intent(
        "Which hospital near Lucknow can handle an emergency C-section?",
        catalog=catalog,
    )
except IntentError as exc:
    result = exc.as_dict()
```

函数调用同样默认加载项目 `.env`，也可通过 `parse_intent(..., env_file=Path("/path/to/custom.env"))` 指定文件。
文件路径默认相对于模块位置，因此从其他工作目录导入模块也能找到两份分类文件。
这是同步模型请求，在异步后端中应放到工作线程或任务队列。

| 配置 | 作用 |
| --- | --- |
| `ARK_API_KEY` | 必填；使用 `.env` 中的 API Key |
| `ARK_MODEL` | 必填；使用 `.env` 中的模型或接入点 ID |
| `ARK_INTENT_TIMEOUT_SECONDS` | 1–600 秒；未设置时使用 `ARK_TIMEOUT_SECONDS`，再默认 180 |
| `ARK_INTENT_MAX_OUTPUT_TOKENS` | 512–32768；未设置时使用 `ARK_MAX_OUTPUT_TOKENS`，再默认 2048 |
| `ARK_INTENT_THINKING` | `disabled` 或 `enabled`；默认 `disabled` |

每次解析发起一次模型请求，不自动重试。只发送用户输入和 116 行可路由分类的 ID、名称与范围。
程序本地校验输出格式、地点文字确实出现在输入中、ID 在允许范围内、服务数量和词典一致性，
再展开完整映射；地点的语义识别和服务选择仍依赖模型，不做外部地址或邮编真实性验证。

离线测试：

```bash
python3 -m unittest -v test_intent_agent
```
