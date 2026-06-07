import asyncio
import sys
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from database.connection import init_db
from utils.logger import logger
from modules import (
    SpiderManager,
    SimilarityMatcher,
    CaseManager,
    EvidenceGenerator,
    WarningLetterManager,
    LitigationManager,
    ReportGenerator,
    BatchLitigationManager,
    IntellectualPropertyManager
)


class ScheduledTasks:
    def __init__(self):
        self.spider_mgr = SpiderManager()
        self.similarity_matcher = SimilarityMatcher()
        self.case_mgr = CaseManager()
        self.evidence_gen = EvidenceGenerator()
        self.warning_mgr = WarningLetterManager()
        self.litigation_mgr = LitigationManager()
        self.report_gen = ReportGenerator()
        self.batch_lit_mgr = BatchLitigationManager()

    def daily_crawl_and_compare(self):
        logger.info("=" * 60)
        logger.info("开始执行每日自动爬取与比对任务")
        logger.info("=" * 60)

        try:
            ip_mgr = IntellectualPropertyManager
            from database.connection import get_db
            from database.models import IPStatusEnum, IntellectualProperty

            with get_db() as db:
                active_ips = db.query(IntellectualProperty).filter(
                    IntellectualProperty.status == IPStatusEnum.ACTIVE
                ).all()

            keywords = []
            for ip in active_ips:
                if ip.name:
                    keywords.append(ip.name)
                if ip.keywords:
                    keywords.extend(ip.keywords)

            keywords = list(set(keywords))[:50]

            if not keywords:
                logger.warning("没有可用的关键词，跳过爬取")
                return

            logger.info(f"获取到 {len(keywords)} 个关键词，开始爬取...")

            products = asyncio.run(self.spider_mgr.crawl_multiple_keywords(keywords))
            saved_count = self.spider_mgr.save_products(products)

            logger.info(f"爬取完成，共保存 {saved_count} 个新商品")

            suspected = self.similarity_matcher.get_suspected_matches()
            if suspected:
                cases = self.case_mgr.batch_create_cases(suspected)
                logger.info(f"比对完成，创建 {len(cases)} 个侵权案件")

                for case in cases:
                    try:
                        self.evidence_gen.generate_evidence_pack(case.id)
                    except Exception as e:
                        logger.error(f"生成证据包失败 {case.case_number}: {e}")
            else:
                logger.info("未发现疑似侵权商品")

        except Exception as e:
            logger.error(f"每日爬取比对任务执行失败: {e}", exc_info=True)

    def process_cases(self):
        logger.info("开始执行案件处理任务")

        try:
            warning_letters = self.warning_mgr.process_low_risk_cases()
            logger.info(f"低风险案件处理完成，发送 {len(warning_letters)} 封警告函")

            litigations = self.litigation_mgr.process_high_risk_cases()
            logger.info(f"高风险案件处理完成，生成 {len(litigations)} 份诉讼文档")

            overdue_cases = self.case_mgr.check_overdue_cases()
            logger.info(f"超期案件检查完成，发现 {len(overdue_cases)} 个超期案件")

        except Exception as e:
            logger.error(f"案件处理任务执行失败: {e}", exc_info=True)

    def weekly_report(self):
        logger.info("开始生成周报告")

        try:
            report = self.report_gen.generate_weekly_report()
            logger.info(f"周报告生成完成: {report.report_week}")
            logger.info(f"  - PDF: {report.pdf_path}")
            logger.info(f"  - Excel: {report.excel_path}")

            suggestions = self.batch_lit_mgr.check_and_generate_batch_suggestions()
            logger.info(f"批量诉讼建议检查完成，生成 {len(suggestions)} 份建议")

        except Exception as e:
            logger.error(f"周报告生成失败: {e}", exc_info=True)

    def health_check(self):
        logger.info("系统健康检查")
        try:
            from database.connection import get_db
            from database.models import InfringementCase
            with get_db() as db:
                case_count = db.query(InfringementCase).count()
            logger.info(f"系统运行正常，当前案件总数: {case_count}")
        except Exception as e:
            logger.error(f"健康检查失败: {e}")


def start_scheduler():
    scheduler = BlockingScheduler(timezone="Asia/Shanghai")
    tasks = ScheduledTasks()

    scheduler.add_job(
        tasks.daily_crawl_and_compare,
        CronTrigger(hour=2, minute=0),
        id="daily_crawl_compare",
        name="每日爬取与比对",
        replace_existing=True
    )

    scheduler.add_job(
        tasks.process_cases,
        CronTrigger(hour=8, minute=0),
        id="daily_case_process",
        name="每日案件处理",
        replace_existing=True
    )

    scheduler.add_job(
        tasks.weekly_report,
        CronTrigger(day_of_week="mon", hour=9, minute=0),
        id="weekly_report",
        name="每周一报告生成",
        replace_existing=True
    )

    scheduler.add_job(
        tasks.health_check,
        IntervalTrigger(hours=6),
        id="health_check",
        name="每6小时健康检查",
        replace_existing=True
    )

    logger.info("调度器已启动")
    logger.info("已配置的定时任务:")
    for job in scheduler.get_jobs():
        logger.info(f"  - {job.name}: {job.trigger}")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("调度器已停止")


def run_once():
    logger.info("执行一次性完整任务")
    tasks = ScheduledTasks()
    tasks.daily_crawl_and_compare()
    tasks.process_cases()


def main():
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "init":
            logger.info("初始化数据库...")
            init_db()
            logger.info("数据库初始化完成")

        elif command == "run":
            init_db()
            run_once()

        elif command == "scheduler":
            init_db()
            start_scheduler()

        elif command == "report":
            init_db()
            tasks = ScheduledTasks()
            tasks.weekly_report()

        else:
            print("使用方法:")
            print("  python main.py init      - 初始化数据库")
            print("  python main.py run       - 执行一次完整任务")
            print("  python main.py scheduler - 启动定时调度器")
            print("  python main.py report    - 生成本周报告")
    else:
        print("请指定命令参数。使用 'python main.py' 查看帮助")


if __name__ == "__main__":
    main()
