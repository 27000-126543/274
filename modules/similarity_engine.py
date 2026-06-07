import jieba
import numpy as np
from typing import List, Tuple, Dict, Any, Optional
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from PIL import Image
import imagehash
from Levenshtein import ratio as levenshtein_ratio
import requests
from io import BytesIO
from config.settings import settings
from database.models import IntellectualProperty, CrawledProduct
from database.connection import get_db
from utils.logger import logger


class TextSimilarityEngine:
    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            tokenizer=lambda x: jieba.lcut(x),
            stop_words=self._get_stop_words(),
            max_features=5000
        )
        self._fitted = False

    def _get_stop_words(self) -> List[str]:
        default_stops = ["的", "了", "是", "在", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"]
        return default_stops

    def levenshtein_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        return levenshtein_ratio(text1, text2)

    def sequence_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        return SequenceMatcher(None, text1, text2).ratio()

    def jaccard_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0
        words1 = set(jieba.lcut(text1))
        words2 = set(jieba.lcut(text2))
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)

    def tfidf_cosine_similarity(self, texts1: List[str], texts2: List[str]) -> np.ndarray:
        all_texts = texts1 + texts2
        if not self._fitted:
            self.vectorizer.fit(all_texts)
            self._fitted = True

        vecs1 = self.vectorizer.transform(texts1)
        vecs2 = self.vectorizer.transform(texts2)
        return cosine_similarity(vecs1, vecs2)

    def compute_text_similarity(self, text1: str, text2: str) -> float:
        if not text1 or not text2:
            return 0.0

        lev_score = self.levenshtein_similarity(text1, text2)
        seq_score = self.sequence_similarity(text1, text2)
        jaccard_score = self.jaccard_similarity(text1, text2)

        weights = [0.3, 0.3, 0.4]
        final_score = lev_score * weights[0] + seq_score * weights[1] + jaccard_score * weights[2]

        return min(final_score, 1.0)


class ImageSimilarityEngine:
    def __init__(self):
        self.hash_size = 8

    def get_image_hash(self, image_source: str, is_url: bool = True) -> Optional[imagehash.ImageHash]:
        try:
            if is_url:
                response = requests.get(image_source, timeout=10)
                img = Image.open(BytesIO(response.content))
            else:
                img = Image.open(image_source)

            img = img.convert("RGB").resize((256, 256))
            return imagehash.phash(img, hash_size=self.hash_size)
        except Exception as e:
            logger.debug(f"获取图片哈希失败: {e}")
            return None

    def compute_image_similarity(self, hash1: Optional[imagehash.ImageHash], hash2: Optional[imagehash.ImageHash]) -> float:
        if hash1 is None or hash2 is None:
            return 0.0

        hamming_distance = hash1 - hash2
        max_distance = self.hash_size * self.hash_size
        similarity = 1.0 - (hamming_distance / max_distance)

        return max(similarity, 0.0)


class SimilarityMatcher:
    def __init__(self):
        self.text_engine = TextSimilarityEngine()
        self.image_engine = ImageSimilarityEngine()
        self.threshold = settings.SIMILARITY_THRESHOLD

    def _prepare_ip_text(self, ip: IntellectualProperty) -> str:
        parts = [ip.name]
        if ip.description:
            parts.append(ip.description)
        if ip.keywords:
            parts.extend(ip.keywords)
        return " ".join(parts)

    def _prepare_product_text(self, product: CrawledProduct) -> str:
        parts = [product.title]
        if product.description:
            parts.append(product.description)
        if product.category:
            parts.append(product.category)
        return " ".join(parts)

    def match_single(self, ip: IntellectualProperty, product: CrawledProduct) -> Dict[str, Any]:
        ip_text = self._prepare_ip_text(ip)
        product_text = self._prepare_product_text(product)

        text_score = self.text_engine.compute_text_similarity(ip_text, product_text)

        image_score = 0.0
        if ip.image_urls and product.image_urls:
            ip_hash = self.image_engine.get_image_hash(ip.image_urls[0])
            prod_hash = self.image_engine.get_image_hash(product.image_urls[0])
            image_score = self.image_engine.compute_image_similarity(ip_hash, prod_hash)

        final_score = text_score * 0.7 + image_score * 0.3

        return {
            "ip_id": ip.id,
            "ip_number": ip.ip_number,
            "ip_name": ip.name,
            "product_id": product.id,
            "product_title": product.title,
            "text_similarity": round(text_score, 4),
            "image_similarity": round(image_score, 4),
            "final_score": round(final_score, 4),
            "is_suspected": final_score >= self.threshold
        }

    def batch_match(
        self,
        ips: List[IntellectualProperty],
        products: List[CrawledProduct]
    ) -> List[Dict[str, Any]]:
        results = []
        suspected_count = 0

        for ip in ips:
            for product in products:
                result = self.match_single(ip, product)
                results.append(result)
                if result["is_suspected"]:
                    suspected_count += 1

        logger.info(f"批量比对完成: {len(ips)}个IP x {len(products)}个商品 = {len(results)}次比对，发现{suspected_count}个疑似侵权")
        return results

    def get_suspected_matches(
        self,
        ips: Optional[List[IntellectualProperty]] = None,
        products: Optional[List[CrawledProduct]] = None
    ) -> List[Dict[str, Any]]:
        with get_db() as db:
            if ips is None:
                from database.models import IPStatusEnum
                ips = db.query(IntellectualProperty).filter(
                    IntellectualProperty.status == IPStatusEnum.ACTIVE
                ).all()

            if products is None:
                from modules.spider_manager import SpiderManager
                spider_mgr = SpiderManager()
                products = spider_mgr.get_pending_products(limit=5000)

        logger.info(f"开始相似度比对: {len(ips)}个知识产权, {len(products)}个待检测商品")

        all_results = self.batch_match(ips, products)
        suspected = [r for r in all_results if r["is_suspected"]]

        return suspected
