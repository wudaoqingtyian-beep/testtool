# 测试数据工厂（Data Factory）

写一个 YAML 文件描述"我想要什么数据"（手机号、姓名、金额、字段之间的关联），跑一条命令就能批量生成，直接写进数据库或导出成文件。测完的数据按批次记录，可以一键清干净。

支持两种用法：命令行工具，或者启动成 HTTP 服务给其他程序调用。

## 主要功能

- **模板造数**：YAML 里声明模型名、字段规则、生成数量，一条命令批量生成
- **15 种内置规则**：手机号、身份证、姓名、uuid、随机金额、时间、递增序列等。想加新规则就是加一个函数再注册一下，不用改其他代码
- **多表依赖造数**：比如订单要挂在真实用户下面，工具会先造用户、再造订单，自动把用户的 id 填进订单。模板之间依赖写成了环会直接报错，不会跑到一半才挂
- **异常数据模式**：加 `--boundary` 参数后，每条正常数据会额外生成一批"捣乱"版本——超长字符串、SQL 注入、越界数值这类，并标好哪些应该被接受、哪些应该被拒绝，方便拿去测接口的校验逻辑
- **批次回滚**：每次造数存一份批次档案（snapshots/ 目录下的 json 文件），测完按批次号删除这批数据。删除时先删订单再删用户，避免外键约束报错
- **两种输出**：写 MySQL（自动对齐表里实际存在的列，超长内容按列定义截断）或导出 CSV / JSON 文件

## 环境要求

- Python 3.10+
- MySQL（只往数据库写数据时才需要；导出文件用不到数据库）

## 安装

```bash
pip install -r requirements.txt
cp config.example.yaml config.yaml   # 填写数据库连接；只用文件导出可以跳过
```

## 快速开始

```bash
# 生成 100 条用户数据写入数据库
python main.py -t templates/user_db.yaml -c 100

# 没配数据库也能玩：导出 CSV 到 exports/ 目录
python main.py -t templates/user.yaml -c 100

# 造正常数据 + 异常数据
python main.py -t templates/demo_db.yaml --boundary

# 查看历史批次 / 回滚某一批
python main.py --list
python main.py --rollback B20260904191220
```

## 模板怎么写

```yaml
model: orders                 # 表名（或导出文件的前缀）
count: 200                    # 生成条数，命令行 -c 可以覆盖
output: database              # database（写库）/ file（导出文件）
file_format: csv              # 导出格式：csv / json
depends_on: user              # 依赖哪个模型（先造 user）
fields:
  order_no: "${uuid}"
  user_id: "${ref(user.id)}"  # 取一个已生成用户的 id 填进来
  amount: "${decimal(0.01, 999.99)}"
  status: "${enum(created, paid, shipped, refunded)}"
  created_at: "${datetime_recent(30d)}"
```

字段值里的 `${规则(参数)}` 会在生成时被替换成真实数据。

## 配置文件

`config.yaml`（模板见 `config.example.yaml`）：

```yaml
database:
  url: "mysql+pymysql://user:password@localhost:3306/dbname?charset=utf8mb4"
  batch_size: 100             # 每批插入多少条
marker:
  field: "env_tag"            # 测试标记字段名
  value: "TEST_DATA"          # 标记值，造的数据都带这个标记，回滚时按它找数据
snapshot_dir: "snapshots"     # 批次档案存放目录
```

## 当成服务用

```bash
uvicorn server:app --host 0.0.0.0 --port 8000   # 自带接口文档页 /docs
```

| 接口 | 说明 |
|---|---|
| GET `/api/v1/health` | 检查服务是否在线 |
| POST `/api/v1/data/generate` | 造数。参数：模板名、条数、是否加异常数据。返回批次号和数据 |
| POST `/api/v1/data/rollback` | 按批次号删掉那次造的数据 |
| GET `/api/v1/data/batches` | 列出历史批次 |

## 项目结构

```
├── main.py                 # 命令行入口
├── server.py               # HTTP 服务入口
├── core/
│   ├── loader.py           # 读模板、检查模板、按依赖排序
│   ├── rules.py            # 规则对照表和 ${} 替换逻辑
│   ├── generator.py        # 生成调度、外键回填
│   ├── boundary.py         # 异常数据生成
│   └── snapshot.py         # 批次档案与回滚
├── output/
│   ├── base.py             # 输出方式的统一接口
│   ├── db_output.py        # 写 MySQL
│   ├── file_output.py      # 导出 CSV/JSON
│   └── cleaner.py          # 按标记删数据
├── templates/              # 模板示例
└── tests/                  # 22 个单元测试
```

## 跑测试

```bash
python -m pytest tests/ -v
```

## 目前做不到的

- 回滚是按"测试标记"整批删的，不是精确到某几条；同一标记造过多次数，回滚一批会把其他批的同标记数据也删掉
- 表需要自己提前建好，工具只插数据不建表
- 异常数据的取值范围只认整串 `${int(...)}` / `${decimal(...)}` 形式的字段
