from cmath import e
import logging
from collections.abc import Generator
from typing import Any
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.alchemy_db_client import get_db_schema
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage

class RookieText2dataTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        model_info= tool_parameters.get('model')
        meta_data = get_db_schema(
            db_type=tool_parameters['db_type'],
            host=tool_parameters['host'],
            port=tool_parameters['port'],
            database=tool_parameters['db_name'],
            username=tool_parameters['username'],
            password=tool_parameters['password'],
        )
        logging.info(f"Found {len(meta_data)} tables: {', '.join(meta_data.keys())}")
        response = self.session.model.llm.invoke(
            model_config=LLMModelConfig(
                provider=model_info.get('provider'),
                model=model_info.get('model'),
                mode=model_info.get('mode'),
                completion_params=model_info.get('completion_params')
            ),
            prompt_messages=[
                SystemPromptMessage(
                    content=f"""你是一位资深数据库工程师兼SQL优化专家，拥有10年以上DBA经验。请根据用户的数据库类型，以及提供的数据库元数据DDL和自然语言需求描述，生成符合企业级标准的优化SQL语句。

                            ## 系统要求：
                            1. 必须严格嵌入提供的DDL元数据{meta_data}，禁止使用任何未声明的表或字段
                            2. 仅返回SELECT语句，禁止包含INSERT/UPDATE/DELETE等DML操作
                            3. 必须使用LIMIT语句进行结果限制，防止数据泄露风险
                            4. 如果用户提出了具体的数据数量，则Limit用户的查询数量，否则Limit 100
                                - MySQL使用`LIMIT n`语法
                                - Oracle使用`ROWNUM <= n`语法
                                - SQL Server使用`TOP n`语法
                                - PostgreSQL使用`FETCH FIRST n ROWS ONLY`语法  
                            5. 所有字段符合对应数据库类型标识符规范

                            ## 优化原则：
                            1. 采用覆盖索引策略，确保查询命中至少2个索引
                                - MySQL采用覆盖索引（Covering Index）
                                - Oracle采用索引组织表（Index Organized Table）
                                - PostgreSQL采用INCLUDE索引（覆盖列） 
                            2. 避免SELECT *，仅返回需求中的必要字段
                            3. 对日期字段使用CURDATE()等函数时需标注时间范围
                                - MySQL使用`CURDATE()`/`NOW()`
                                - PostgreSQL使用`CURRENT_DATE`/`CURRENT_TIMESTAMP`
                            4. 多表关联必须使用INNER JOIN，禁止LEFT/RIGHT JOIN

                            ## 验证机制：
                            1. 生成后自动检查表是否存在，若不存在则抛出错误
                            2. 条件字段值必须存在于目标表中，否则提示字段不存在
                            3. 自动生成EXPLAIN计划，确保type列显示为ref或eq_ref
                            4. 仅返回生成的SQL语句，禁止返回注释、DDL、描述等与SQL无关内容
                            5. 禁止使用任何转义字符（如''或\"）
                            6. 禁止在开头和结尾使用``` ```包裹SQL语句

                            ## 输出示例（MySQL）：
                            SELECT 
                                `order_id` AS 订单编号,
                                `amount` * 1.05 AS 含税金额  
                            FROM 
                                `orders` o
                            INNER JOIN 
                                `customers` c ON o.`customer_id` = c.`id`  
                            WHERE 
                                o.`status` = 'paid' 
                                AND c.`region` = 'Asia'
                                AND o.`created_at` BETWEEN '2025-01-01' AND CURDATE()
                            LIMIT 100;

                            ## 输出示例（PostgreSQL）：
                            SELECT 
                                "order_id" AS 订单编号,
                                "amount" * 1.05 AS 含税金额  
                            FROM 
                                "orders" o
                            INNER JOIN 
                                "customers" c ON o."customer_id" = c."id"  
                            WHERE 
                                o."status" = 'paid' 
                                AND c."region" = 'Asia'
                                AND o."created_at" BETWEEN '2025-01-01' AND CURRENT_DATE
                            FETCH FIRST 100 ROWS ONLY;
                         """
                ),
                UserPromptMessage(
                    content=f"用户的数据库类型为：{tool_parameters.get('db_type')}, 用户想要查询的数据需求为：{tool_parameters.get('query')}"
                )
            ],
            stream=False
        )

        excute_sql = response.message.content
        logging.info(f"Generated SQL: {excute_sql}")
        yield self.create_text_message(self._extract_sql_from_text(excute_sql))

    def _extract_sql_from_text(self, text: str) -> str:
        """提取 ``的```sql...```代码块中的SQL内容（若存在）"""
        import re
        pattern = r'```sql\s*(.*?)\s*```'
        match = re.search(pattern, text, flags=re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
