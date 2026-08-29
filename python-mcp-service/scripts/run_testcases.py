"""
端到端测试用例脚本。

直接调用 AnalysisRunner（等价于 MCP enterprise_analysis 工具），
对 3 条复合业务需求做完整链路验证，打印结构化结果与量化指标。

用法（需 Java 主服务已启动以提供 /internal 数据；否则子 Agent 走无数据分支）：
    python -m scripts.run_testcases
"""
from __future__ import annotations

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.graph.runner import get_runner  # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")

# 3 条复合业务测试需求
TEST_CASES = [
    {
        "name": "用例1-数据库统计+计算+校验",
        "question": "统计近三个月各部门销售总额与环比增长，标注是否存在销量暴跌风险",
    },
    {
        "name": "用例2-文档+数据库联合分析",
        "question": "结合销售管理制度文档，分析当前库存赤字商品是否违反安全库存规定",
    },
    {
        "name": "用例3-低置信度触发反思重试",
        "question": "分析上个季度海外仓周转率与本地政策文档的合规差异",
    },
]


def main() -> None:
    runner = get_runner()
    for i, case in enumerate(TEST_CASES, start=1):
        print("=" * 80)
        print(f"[{case['name']}] {case['question']}")
        result = runner.analyze(
            question=case["question"],
            user_id=1,
            dept_id=1,
            dept_ids=None,           # 管理员全量
            session_id=f"testcase-{i}",
            callback_base_url=None,  # 使用默认配置
            internal_api_key=None,
        )
        summary = {
            "success": result["success"],
            "confidence_score": result["confidence_score"],
            "risk_tags": result["risk_tags"],
            "retry_count": result["retry_count"],
            "token_total": result["token_total"],
            "cache_hit": result["cache_hit"],
            "error_code": result.get("error_code"),
            "cost_ms": result["cost_ms"],
        }
        print("量化指标 =>", json.dumps(summary, ensure_ascii=False))
        print("报告预览 =>")
        print((result.get("report") or "")[:600])
    print("=" * 80)
    print("全部测试用例执行完成。")


if __name__ == "__main__":
    main()
