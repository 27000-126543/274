"""
使用示例：知识产权侵权监测与维权管理系统
"""

import sys
from datetime import date

sys.path.insert(0, '.')

from database.connection import init_db, get_db
from database.models import (
    InfringementStatusEnum, RiskLevelEnum, IPTypeEnum, IPStatusEnum
)
from modules import (
    IntellectualPropertyManager,
    SpiderManager,
    SimilarityMatcher,
    EvidenceGenerator,
    CaseManager,
    WarningLetterManager,
    LitigationManager,
    LedgerManager,
    OfflineClueManager,
    ReportGenerator,
    BatchLitigationManager,
    QueryManager,
    ExportManager
)
from utils.logger import logger


def example_1_manage_ip():
    """示例1：知识产权库管理"""
    logger.info("=== 示例1：知识产权库管理 ===")

    with get_db() as db:
        ip_mgr = IntellectualPropertyManager(db)

        new_ip = ip_mgr.add_ip(
            ip_type=IPTypeEnum.PATENT,
            ip_number="ZL202410000001.0",
            name="新型节能技术",
            owner="示例科技有限公司",
            description="本发明涉及一种新型节能技术，可应用于多种电子设备。",
            application_date=date(2024, 1, 1),
            grant_date=date(2024, 6, 1),
            expiration_date=date(2044, 1, 1),
            category="节能技术",
            keywords=["节能", "环保", "新能源", "电子设备"]
        )
        logger.info(f"添加知识产权: {new_ip.ip_number} - {new_ip.name}")

        all_ips = ip_mgr.list_ips(status=IPStatusEnum.ACTIVE)
        logger.info(f"当前有效知识产权总数: {len(all_ips)}")

        for ip in all_ips[:3]:
            logger.info(f"  - {ip.ip_number}: {ip.name} ({ip.ip_type.value})")


def example_2_crawl_and_compare():
    """示例2：爬虫抓取与相似度比对"""
    logger.info("\n=== 示例2：爬虫抓取与相似度比对 ===")

    import asyncio
    spider_mgr = SpiderManager()

    keywords = ["智能穿戴设备", "节能技术"]
    logger.info(f"开始爬取关键词: {keywords}")
    products = asyncio.run(spider_mgr.crawl_multiple_keywords(keywords))
    saved_count = spider_mgr.save_products(products)
    logger.info(f"爬取完成，保存了 {saved_count} 个商品")

    similarity_matcher = SimilarityMatcher()
    suspected = similarity_matcher.get_suspected_matches()
    logger.info(f"发现 {len(suspected)} 个疑似侵权商品")

    for match in suspected[:5]:
        logger.info(
            f"  - 相似度: {match['final_score']*100:.1f}% | "
            f"IP: {match['ip_name']} | "
            f"商品: {match['product_title'][:30]}..."
        )


def example_3_create_case():
    """示例3：创建侵权案件并生成证据包"""
    logger.info("\n=== 示例3：创建侵权案件 ===")

    case_mgr = CaseManager()
    evidence_gen = EvidenceGenerator()

    with get_db() as db:
        from database.models import IntellectualProperty, CrawledProduct, IPStatusEnum
        ip = db.query(IntellectualProperty).filter(
            IntellectualProperty.status == IPStatusEnum.ACTIVE
        ).first()
        product = db.query(CrawledProduct).first()

        if ip and product:
            case = case_mgr.create_infringement_case(
                ip_id=ip.id,
                product_id=product.id,
                similarity_score=0.88,
                source_type="manual",
                notes="手动创建的测试案件"
            )
            logger.info(f"创建案件: {case.case_number}, 风险等级: {case.risk_level.value}")

            evidence_path = evidence_gen.generate_evidence_pack(case.id)
            if evidence_path:
                logger.info(f"证据包已生成: {evidence_path}")


def example_4_send_warning():
    """示例4：发送警告函"""
    logger.info("\n=== 示例4：发送警告函 ===")

    warning_mgr = WarningLetterManager()
    letters = warning_mgr.process_low_risk_cases()
    logger.info(f"处理低风险案件，发送 {len(letters)} 封警告函")

    for letter in letters:
        logger.info(f"  - 警告函编号: {letter.letter_number}, 发送至: {letter.send_email}")


def example_5_litigation():
    """示例5：生成诉讼文档"""
    logger.info("\n=== 示例5：生成诉讼文档 ===")

    litigation_mgr = LitigationManager()
    litigations = litigation_mgr.process_high_risk_cases()
    logger.info(f"处理高风险案件，生成 {len(litigations)} 份诉讼文档")

    for lit in litigations:
        logger.info(f"  - 诉讼编号: {lit.litigation_number}")
        logger.info(f"    起诉状: {lit.litigation_doc_path}")
        logger.info(f"    预分析: {lit.pre_analysis_path}")


def example_6_offline_clue():
    """示例6：录入线下侵权线索"""
    logger.info("\n=== 示例6：录入线下侵权线索 ===")

    clue_mgr = OfflineClueManager()

    clue = clue_mgr.add_offline_clue(
        infringing_party_name="某某电子市场A12摊位",
        infringing_content="销售仿冒我司专利产品的智能手环，外观与功能高度相似",
        infringing_location="深圳市福田区华强北电子市场",
        discovery_date=date.today(),
        reporter="市场巡查员 王某某",
        contact_info="13800000000",
        notes="现场购买了样品，已留存购买凭证"
    )
    logger.info(f"新增线下线索: {clue.clue_number}")
    logger.info(f"  是否重复: {'是' if clue.is_duplicate else '否'}")
    logger.info(f"  当前状态: {clue.status}")

    pending_clues = clue_mgr.get_pending_clues()
    logger.info(f"待处理线下线索总数: {len(pending_clues)}")


def example_7_ledger():
    """示例7：维权台账管理"""
    logger.info("\n=== 示例7：维权台账管理 ===")

    ledger_mgr = LedgerManager()

    with get_db() as db:
        from database.models import InfringementCase
        case = db.query(InfringementCase).first()

        if case:
            entry = ledger_mgr.add_ledger_entry(
                case_id=case.id,
                record_date=date.today(),
                compensation_amount=50000.00,
                attorney_fee=8000.00,
                court_fee=2000.00,
                evidence_fee=1500.00,
                other_cost=500.00,
                payment_status="completed",
                notes="和解赔偿已到账"
            )
            logger.info(f"新增台账记录:")
            logger.info(f"  赔偿金额: {entry.compensation_amount:,.2f} 元")
            logger.info(f"  总成本: {entry.total_cost:,.2f} 元")
            logger.info(f"  净收益: {entry.net_amount:,.2f} 元")

    summary = ledger_mgr.get_ledger_summary()
    logger.info(f"\n台账汇总:")
    logger.info(f"  记录总数: {summary['entry_count']}")
    logger.info(f"  累计赔偿: {summary['total_compensation']:,.2f} 元")
    logger.info(f"  累计成本: {summary['total_cost']:,.2f} 元")
    logger.info(f"  累计净收益: {summary['total_net_amount']:,.2f} 元")


def example_8_report():
    """示例8：生成周报告"""
    logger.info("\n=== 示例8：生成周报告 ===")

    report_gen = ReportGenerator()
    report = report_gen.generate_weekly_report()

    logger.info(f"周报告生成完成: {report.report_week}")
    logger.info(f"  统计周期: {report.start_date} - {report.end_date}")
    logger.info(f"  新增案件: {report.new_cases} 件")
    logger.info(f"  结案: {report.closed_cases} 件")
    logger.info(f"  成功率: {report.success_rate:.1f}%")
    logger.info(f"  平均响应时长: {report.avg_response_time_hours:.1f} 小时")
    logger.info(f"  PDF报告: {report.pdf_path}")
    logger.info(f"  Excel报告: {report.excel_path}")


def example_9_batch_litigation():
    """示例9：批量诉讼建议"""
    logger.info("\n=== 示例9：批量诉讼建议 ===")

    batch_mgr = BatchLitigationManager()

    repeat_offenders = batch_mgr.detect_repeat_offenders(min_complaints=2)
    logger.info(f"发现 {len(repeat_offenders)} 个多次侵权方")

    for party in repeat_offenders:
        logger.info(f"  - {party.name}: 累计被投诉 {party.complaint_count} 次")

    suggestions = batch_mgr.check_and_generate_batch_suggestions()
    logger.info(f"生成 {len(suggestions)} 份批量诉讼建议")

    for suggestion in suggestions:
        logger.info(f"  - 批次ID: {suggestion['batch_id']}")
        logger.info(f"    侵权方: {suggestion['infringing_party']['name']}")
        logger.info(f"    关联案件: {suggestion['analysis']['total_cases']} 件")


def example_10_query_export():
    """示例10：查询与导出"""
    logger.info("\n=== 示例10：查询与导出 ===")

    query_mgr = QueryManager()
    export_mgr = ExportManager()

    cases = query_mgr.query_cases(
        risk_level=RiskLevelEnum.HIGH,
        limit=10
    )
    logger.info(f"查询高风险案件，找到 {len(cases)} 件")

    for case in cases[:3]:
        logger.info(f"  - {case.case_number}: {case.status.value}")

    if cases:
        case_detail = query_mgr.query_case_full_lifecycle(cases[0].id)
        logger.info(f"\n案件全生命周期信息:")
        logger.info(f"  案件编号: {case_detail['case_info']['case_number']}")
        logger.info(f"  警告函数量: {len(case_detail['warning_letters'])}")
        logger.info(f"  诉讼记录: {len(case_detail['litigations'])}")
        logger.info(f"  操作日志: {len(case_detail['operation_logs'])} 条")

        export_path = export_mgr.export_cases_to_excel(cases)
        logger.info(f"\n案件数据已导出: {export_path}")

        export_path2 = export_mgr.batch_export_full_cases([c.id for c in cases[:3]])
        logger.info(f"全生命周期数据已导出: {export_path2}")


def run_all_examples():
    """运行所有示例"""
    logger.info("知识产权侵权监测与维权管理系统 - 使用示例")
    logger.info("=" * 70)

    init_db()

    example_1_manage_ip()
    example_3_create_case()
    example_4_send_warning()
    example_5_litigation()
    example_6_offline_clue()
    example_7_ledger()
    example_8_report()
    example_9_batch_litigation()
    example_10_query_export()

    logger.info("\n" + "=" * 70)
    logger.info("所有示例执行完成！")


if __name__ == "__main__":
    run_all_examples()
