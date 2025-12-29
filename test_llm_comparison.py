"""多 LLM 对比测试框架

用于测试不同 LLM 驱动下 GUI Agent 的表现
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

from agent import Agent
from browser import Browser
from llm import ChatOpenAI, ChatAnthropic, ChatDoubao, BaseLLM

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """测试结果数据类"""
    llm_name: str
    task: str
    success: bool
    total_steps: int
    total_time: float
    final_result: Optional[str]
    error: Optional[str]
    history: List[Dict[str, Any]]
    start_time: str
    end_time: str


class LLMTestRunner:
    """LLM 测试运行器"""
    
    def __init__(self, output_dir: str = "test_results"):
        """
        初始化测试运行器
        
        Args:
            output_dir: 测试结果输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.results: List[TestResult] = []
    
    def create_llm(self, llm_type: str, api_key: Optional[str] = None) -> BaseLLM:
        """创建 LLM 实例"""
        if llm_type == "openai":
            return ChatOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        elif llm_type == "anthropic":
            return ChatAnthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        elif llm_type == "doubao":
            return ChatDoubao(api_key=api_key or os.getenv("DOUBAO_API_KEY"))
        else:
            raise ValueError(f"不支持的 LLM 类型: {llm_type}")
    
    async def run_single_test(
        self,
        llm_type: str,
        task: str,
        api_key: Optional[str] = None,
        max_steps: int = 20,
        headless: bool = True
    ) -> TestResult:
        """
        运行单个测试
        
        Args:
            llm_type: LLM 类型 (openai, anthropic, doubao)
            task: 任务描述
            api_key: API 密钥（可选）
            max_steps: 最大执行步数
            headless: 是否无头模式
        
        Returns:
            TestResult: 测试结果
        """
        logger.info(f"开始测试: {llm_type} - {task[:50]}...")
        
        start_time = datetime.now().isoformat()
        start_timestamp = time.time()
        
        browser = None
        try:
            # 创建 LLM 和浏览器
            llm = self.create_llm(llm_type, api_key)
            browser = Browser(headless=headless)
            
            # 创建 Agent
            agent = Agent(
                task=task,
                llm=llm,
                browser=browser,
                max_steps=max_steps
            )
            
            # 运行任务
            result = await agent.run()
            
            end_timestamp = time.time()
            end_time = datetime.now().isoformat()
            total_time = end_timestamp - start_timestamp
            
            # 构建测试结果
            test_result = TestResult(
                llm_name=llm_type,
                task=task,
                success=result.get("success", False),
                total_steps=len(agent.history),
                total_time=total_time,
                final_result=result.get("final_result"),
                error=result.get("error"),
                history=agent.history,
                start_time=start_time,
                end_time=end_time
            )
            
            logger.info(
                f"测试完成: {llm_type} - "
                f"成功: {test_result.success}, "
                f"步数: {test_result.total_steps}, "
                f"耗时: {test_result.total_time:.2f}s"
            )
            
            return test_result
            
        except Exception as e:
            end_timestamp = time.time()
            end_time = datetime.now().isoformat()
            total_time = end_timestamp - start_timestamp
            
            logger.error(f"测试失败: {llm_type} - {str(e)}")
            
            return TestResult(
                llm_name=llm_type,
                task=task,
                success=False,
                total_steps=0,
                total_time=total_time,
                final_result=None,
                error=str(e),
                history=[],
                start_time=start_time,
                end_time=end_time
            )
        
        finally:
            # 清理浏览器
            if browser:
                try:
                    await browser.close()
                except:
                    pass
    
    async def run_comparison_test(
        self,
        tasks: List[str],
        llm_types: List[str],
        api_keys: Optional[Dict[str, str]] = None,
        max_steps: int = 20,
        headless: bool = True,
        delay_between_tests: float = 2.0
    ) -> List[TestResult]:
        """
        运行对比测试
        
        Args:
            tasks: 任务列表
            llm_types: LLM 类型列表
            api_keys: API 密钥字典 {llm_type: api_key}
            max_steps: 最大执行步数
            headless: 是否无头模式
            delay_between_tests: 测试之间的延迟（秒）
        
        Returns:
            List[TestResult]: 所有测试结果
        """
        api_keys = api_keys or {}
        all_results: List[TestResult] = []
        
        logger.info(f"开始对比测试: {len(tasks)} 个任务 × {len(llm_types)} 个 LLM")
        
        for task_idx, task in enumerate(tasks, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"任务 {task_idx}/{len(tasks)}: {task}")
            logger.info(f"{'='*60}\n")
            
            for llm_idx, llm_type in enumerate(llm_types, 1):
                logger.info(f"\n--- LLM {llm_idx}/{len(llm_types)}: {llm_type} ---")
                
                result = await self.run_single_test(
                    llm_type=llm_type,
                    task=task,
                    api_key=api_keys.get(llm_type),
                    max_steps=max_steps,
                    headless=headless
                )
                
                all_results.append(result)
                self.results.append(result)
                
                # 测试之间的延迟
                if delay_between_tests > 0:
                    await asyncio.sleep(delay_between_tests)
        
        return all_results
    
    def save_results(self, filename: Optional[str] = None):
        """保存测试结果到 JSON 文件"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"test_results_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        # 转换为字典格式
        results_dict = {
            "test_time": datetime.now().isoformat(),
            "results": [asdict(result) for result in self.results]
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(results_dict, f, ensure_ascii=False, indent=2)
        
        logger.info(f"测试结果已保存到: {filepath}")
        return filepath
    
    def generate_report(self, output_file: Optional[str] = None):
        """生成对比报告"""
        if not self.results:
            logger.warning("没有测试结果可生成报告")
            return
        
        # 按 LLM 分组统计
        llm_stats: Dict[str, Dict[str, Any]] = {}
        
        for result in self.results:
            llm_name = result.llm_name
            if llm_name not in llm_stats:
                llm_stats[llm_name] = {
                    "total_tests": 0,
                    "successful_tests": 0,
                    "failed_tests": 0,
                    "total_steps": 0,
                    "total_time": 0.0,
                    "avg_steps": 0.0,
                    "avg_time": 0.0,
                    "success_rate": 0.0
                }
            
            stats = llm_stats[llm_name]
            stats["total_tests"] += 1
            if result.success:
                stats["successful_tests"] += 1
            else:
                stats["failed_tests"] += 1
            
            stats["total_steps"] += result.total_steps
            stats["total_time"] += result.total_time
        
        # 计算平均值
        for llm_name, stats in llm_stats.items():
            if stats["total_tests"] > 0:
                stats["avg_steps"] = stats["total_steps"] / stats["total_tests"]
                stats["avg_time"] = stats["total_time"] / stats["total_tests"]
                stats["success_rate"] = stats["successful_tests"] / stats["total_tests"] * 100
        
        # 生成报告文本
        report_lines = [
            "=" * 80,
            "LLM 对比测试报告",
            "=" * 80,
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"总测试数: {len(self.results)}",
            "",
            "总体统计:",
            "-" * 80,
        ]
        
        for llm_name, stats in sorted(llm_stats.items()):
            report_lines.extend([
                f"\n{llm_name.upper()}:",
                f"  总测试数: {stats['total_tests']}",
                f"  成功: {stats['successful_tests']}",
                f"  失败: {stats['failed_tests']}",
                f"  成功率: {stats['success_rate']:.2f}%",
                f"  平均步数: {stats['avg_steps']:.2f}",
                f"  平均耗时: {stats['avg_time']:.2f}s",
                f"  总耗时: {stats['total_time']:.2f}s",
            ])
        
        report_lines.extend([
            "",
            "=" * 80,
            "详细结果:",
            "=" * 80,
        ])
        
        # 按任务分组显示详细结果
        tasks = set(r.task for r in self.results)
        for task in sorted(tasks):
            report_lines.append(f"\n任务: {task}")
            report_lines.append("-" * 80)
            
            task_results = [r for r in self.results if r.task == task]
            for result in task_results:
                status = "✓ 成功" if result.success else "✗ 失败"
                report_lines.append(
                    f"  {result.llm_name:15s} | {status:8s} | "
                    f"步数: {result.total_steps:3d} | "
                    f"耗时: {result.total_time:6.2f}s"
                )
                if result.error:
                    report_lines.append(f"    错误: {result.error}")
        
        report_text = "\n".join(report_lines)
        
        # 保存报告
        if not output_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"test_report_{timestamp}.txt"
        
        report_path = self.output_dir / output_file
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)
        
        # 打印报告
        print("\n" + report_text)
        logger.info(f"测试报告已保存到: {report_path}")
        
        return report_path


async def main():
    """主函数 - 示例测试"""
    
    # 测试任务列表
    test_tasks = [
        "打开百度首页并搜索 'Python 教程'",
        "访问 https://www.example.com 并提取页面标题",
    ]
    
    # 要测试的 LLM 列表
    llm_types = ["doubao", "openai", "anthropic"]
    
    # API 密钥（如果不在环境变量中）
    api_keys = {
        # "doubao": "your-doubao-api-key",
        # "openai": "your-openai-api-key",
        # "anthropic": "your-anthropic-api-key",
    }
    
    # 创建测试运行器
    runner = LLMTestRunner(output_dir="test_results")
    
    # 运行对比测试
    results = await runner.run_comparison_test(
        tasks=test_tasks,
        llm_types=llm_types,
        api_keys=api_keys,
        max_steps=20,
        headless=True,  # 设置为 False 可以看到浏览器操作
        delay_between_tests=2.0
    )
    
    # 保存结果
    runner.save_results()
    
    # 生成报告
    runner.generate_report()


if __name__ == "__main__":
    asyncio.run(main())

