import asyncio
import unittest
from pydantic import ValidationError
import test_cosmetic_recommendation as f
from app.schemas.cosmetic import CosmeticPreviewRequest
from app.services.cosmetic_recommendation import RecommendationInputError


def example():
    return [dict(metric_code=code, metric_name=name, score=score,
                 category_name=category, higher_is_better=direction)
            for code, name, score, category, direction in [
                ('moisture','수분',50,'보통',True), ('redness','홍조',15,'양호',False),
                ('brightness','밝기',71,'양호',True), ('trouble','트러블',92,'개선 필요',False),
                ('uniformity','균일도',91,'양호',True)]]


class SkinContractTests(unittest.TestCase):
    def test_example_defers_trouble(self):
        r = f.run([f.product()], CosmeticPreviewRequest(scores=example()))
        self.assertEqual((r.target_count, r.scorable_target_count), (1,0))
        self.assertEqual(r.deferred_metrics, ['trouble'])
        self.assertEqual(r.recommendations, [])

    def test_only_moisture_matches_actual_photo_scores(self):
        rows=example()
        for row in rows:
            if row['metric_code'] in {'moisture','brightness','uniformity'}:
                row.update(score=20, category_name='개선 필요')
        r=f.run([f.product()], CosmeticPreviewRequest(scores=rows))
        self.assertEqual([m.metric_code for m in r.recommendations[0].matches], ['moisture'])
        self.assertEqual(set(r.deferred_metrics), {'brightness','uniformity','trouble'})

    def test_missing_moisture(self):
        r=f.run([], CosmeticPreviewRequest(scores=example()[1:]))
        self.assertEqual(r.missing_metrics, ['moisture'])
        self.assertEqual(len(r.assessments),4)

    def test_invalid_array(self):
        for change in ['duplicate','missing','unknown','bool_score','range','direction_type']:
            rows=example()
            if change=='duplicate': rows[0]=rows[1]
            if change=='missing': rows.pop(1)
            if change=='unknown': rows[0]['metric_code']='other'
            if change=='bool_score': rows[0]['score']=True
            if change=='range': rows[0]['score']=101
            if change=='direction_type': rows[0]['higher_is_better']='true'
            with self.subTest(change=change), self.assertRaises(ValidationError):
                CosmeticPreviewRequest(scores=rows)

    def test_direction_and_label_mismatch(self):
        for key,value in [('higher_is_better',False),('category_name','양호')]:
            rows=example(); rows[0][key]=value
            with self.assertRaises(RecommendationInputError):
                f.run([],CosmeticPreviewRequest(scores=rows))

    def test_default_object_and_no_array_legacy(self):
        r=f.run([f.product()],CosmeticPreviewRequest(scores=f.request().scores))
        self.assertEqual(r.recommendations[0].match_count,1)
        with self.assertRaises(ValidationError):
            CosmeticPreviewRequest(scores=example(),score_semantics='development_assumption')


class SkinContractApiTests(unittest.TestCase):
    setUp = f.ApiDatabaseTests.setUp
    tearDown = f.ApiDatabaseTests.tearDown
    def test_example_api(self):
        status,data=asyncio.run(f.asgi_request({'scores':example()}))
        self.assertEqual(status,200)
        self.assertEqual(data['score_semantics'],'photo_v1')
        self.assertEqual(data['deferred_metrics'],['trouble'])

    def test_mismatch_api(self):
        rows=example();rows[3]['category_name']='양호'
        status,_=asyncio.run(f.asgi_request({'scores':rows}))
        self.assertEqual(status,422)
