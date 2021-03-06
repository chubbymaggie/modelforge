import datetime
import os
import pickle
import tempfile
import unittest

import asdf
import numpy
from scipy.sparse import csr_matrix

import modelforge.gcs_backend
from modelforge import generate_meta
from modelforge.backends import create_backend
from modelforge.gcs_backend import GCSBackend
from modelforge.model import merge_strings, split_strings, \
    assemble_sparse_matrix, disassemble_sparse_matrix, Model, write_model
from modelforge.models import GenericModel
from modelforge.tests.fake_requests import FakeRequests
from modelforge.tests.test_dump import TestModel


class Model1(Model):
    def _load_tree(self, tree):
        pass

    def dump(self):
        return "model1"


class Model2(Model):
    NAME = "model2"

    def _load_tree(self, tree):
        pass

    def dump(self):
        return "model2"


class Model3(Model):
    def _load_tree(self, tree):
        pass


class Model4(Model):
    def dump(self):
        return str(self.xxx)


class Model5(Model):
    NAME = "aux"

    def _load_tree(self, tree):
        pass


class Model6(Model5):
    NAME = "docfreq"

    def _load_tree(self, tree):
        pass


class Model7(Model6):
    NAME = "xxx"

    def _load_tree(self, tree):
        pass


def get_path(name):
    return os.path.join(os.path.dirname(__file__), name)


class ModelTests(unittest.TestCase):
    DOCFREQ_PATH = "test.asdf"

    def setUp(self):
        self.backend = create_backend()

    def test_file(self):
        model = GenericModel(source=get_path(self.DOCFREQ_PATH))
        self._validate_meta(model)

    def test_id(self):
        def route(url):
            if GCSBackend.INDEX_FILE in url:
                return '{"models": {"docfreq": {' \
                       '"f64bacd4-67fb-4c64-8382-399a8e7db52a": ' \
                       '{"url": "https://xxx"}}}}'.encode()
            self.assertEqual("https://xxx", url)
            with open(get_path(self.DOCFREQ_PATH), "rb") as fin:
                return fin.read()

        modelforge.gcs_backend.requests = FakeRequests(route)
        model = GenericModel(source="f64bacd4-67fb-4c64-8382-399a8e7db52a",
                             backend=self.backend)
        self._validate_meta(model)

    def test_url(self):
        def route(url):
            self.assertEqual("https://xxx", url)
            with open(get_path(self.DOCFREQ_PATH), "rb") as fin:
                return fin.read()

        modelforge.gcs_backend.requests = FakeRequests(route)
        model = GenericModel(source="https://xxx", backend=self.backend)
        self._validate_meta(model)

    def test_auto(self):
        class FakeModel(GenericModel):
            NAME = "docfreq"

        def route(url):
            if GCSBackend.INDEX_FILE in url:
                return '{"models": {"docfreq": {' \
                       '"f64bacd4-67fb-4c64-8382-399a8e7db52a": ' \
                       '{"url": "https://xxx"}, ' \
                       '"default": "f64bacd4-67fb-4c64-8382-399a8e7db52a"' \
                       '}}}'.encode()
            self.assertEqual("https://xxx", url)
            with open(get_path(self.DOCFREQ_PATH), "rb") as fin:
                return fin.read()

        modelforge.gcs_backend.requests = FakeRequests(route)
        model = FakeModel(backend=create_backend())
        self._validate_meta(model)

    def test_init_with_model(self):
        model1 = Model1().load(source=get_path(self.DOCFREQ_PATH))
        # init with correct model
        Model1(source=model1)
        # init with wrong model
        with self.assertRaises(TypeError):
            Model2().load(source=model1)

    def test_repr_str(self):
        path = get_path(self.DOCFREQ_PATH)
        model = Model1().load(source=path)
        repr1 = repr(model)
        try:
            self.assertIn("test_model.py].Model1().load(source=\"%s\")" % path, repr1)
        except AssertionError:
            self.assertEqual("modelforge.tests.test_model.Model1().load(source=\"%s\")"
                             % path, repr1)
        str1 = str(model)
        self.assertEqual(len(str1.split("\n")), 6)
        self.assertIn("\nmodel1", str1)
        self.assertIn("'uuid': 'f64bacd4-67fb-4c64-8382-399a8e7db52a'", str1)
        model = Model3().load(source=path)
        str2 = str(model)
        self.assertEqual(len(str2.split("\n")), 5)
        model = TestModel().load(source=path)
        repr2 = repr(model)
        self.assertEqual("modelforge.tests.test_dump.TestModel().load(source=\"%s\")"
                         % path, repr2)

    def test_get_dependency(self):
        model = Model1().load(source=get_path(self.DOCFREQ_PATH))
        model.meta["dependencies"] = [{"model": "xxx", "uuid": "yyy"},
                                      {"model": "zzz", "uuid": None}]
        self.assertEqual(model.dep("xxx")["uuid"], "yyy")

    def _validate_meta(self, model):
        meta = model.meta
        self.assertIsInstance(meta, dict)
        self.assertEqual(meta, {
            'created_at': datetime.datetime(2017, 6, 19, 9, 59, 14, 766638),
            'dependencies': [],
            'model': 'docfreq',
            'uuid': 'f64bacd4-67fb-4c64-8382-399a8e7db52a',
            'version': [1, 0, 0]})

    def test_uninitialized_dump(self):
        text = str(Model4())
        try:
            self.assertIn("test_model.py].Model4().load(source=None)", text)
        except AssertionError:
            self.assertEqual("modelforge.tests.test_model.Model4().load(source=None)", text)

    def test_name_check(self):
        Model5().load(source=get_path(self.DOCFREQ_PATH))
        Model6().load(source=get_path(self.DOCFREQ_PATH))
        with self.assertRaises(ValueError):
            Model7().load(source=get_path(self.DOCFREQ_PATH))

    def test_derive(self):
        path = get_path(self.DOCFREQ_PATH)
        model = Model1().load(source=path)
        m2 = model.derive()
        self.assertEqual(m2.version, [1, 0, 1])
        model.derive((2, 0, 0))
        self.assertEqual(m2.version, [2, 0, 0])
        with self.assertRaises(ValueError):
            model.derive("1.2.3")

    def test_props(self):
        path = get_path(self.DOCFREQ_PATH)
        model = Model1().load(source=path)
        for n in ("description", "references", "extra", "parent", "license"):
            with self.assertRaises(KeyError):
                getattr(model, n)
        self.assertEqual(model.version, [1, 0, 0])
        self.assertEqual(model.created_at, datetime.datetime(2017, 6, 19, 9, 59, 14, 766638))


class SerializationTests(unittest.TestCase):
    DOCFREQ_PATH = "test.asdf"

    def test_merge_strings(self):
        strings = ["a", "bc", "def"]
        merged = merge_strings(strings)
        self.assertIsInstance(merged, dict)
        self.assertIn("strings", merged)
        self.assertIn("lengths", merged)
        self.assertIsInstance(merged["strings"], numpy.ndarray)
        self.assertEqual(merged["strings"].shape, (1,))
        self.assertEqual(merged["strings"][0], b"abcdef")
        self.assertIsInstance(merged["lengths"], numpy.ndarray)
        self.assertEqual(merged["lengths"].shape, (3,))
        self.assertEqual(merged["lengths"][0], 1)
        self.assertEqual(merged["lengths"][1], 2)
        self.assertEqual(merged["lengths"][2], 3)

    def test_split_strings(self):
        strings = split_strings({
            "strings": numpy.array([b"abcdef"]),
            "lengths": numpy.array([1, 2, 3])
        })
        self.assertEqual(strings, ["a", "bc", "def"])

    def test_invalid_merge_strings(self):
        with self.assertRaises(TypeError):
            merge_strings("abcd")
        with self.assertRaises(TypeError):
            merge_strings([0, 1, 2, 3])

    def test_merge_bytes(self):
        strings = [b"a", b"bc", b"def"]
        merged = merge_strings(strings)
        self.assertIsInstance(merged, dict)
        self.assertIn("strings", merged)
        self.assertIn("lengths", merged)
        self.assertEqual(merged["str"], False)
        self.assertIsInstance(merged["strings"], numpy.ndarray)
        self.assertEqual(merged["strings"].shape, (1,))
        self.assertEqual(merged["strings"][0], b"abcdef")
        self.assertIsInstance(merged["lengths"], numpy.ndarray)
        self.assertEqual(merged["lengths"].shape, (3,))
        self.assertEqual(merged["lengths"][0], 1)
        self.assertEqual(merged["lengths"][1], 2)
        self.assertEqual(merged["lengths"][2], 3)

    def test_split_bytes(self):
        strings = split_strings({
            "strings": numpy.array([b"abcdef"]),
            "lengths": numpy.array([1, 2, 3]),
            "str": False
        })
        self.assertEqual(strings, [b"a", b"bc", b"def"])

    def test_disassemble_sparse_matrix(self):
        arr = numpy.zeros((10, 10), dtype=numpy.float32)
        numpy.random.seed(0)
        arr[numpy.random.randint(0, 10, (50, 2))] = 1
        mat = csr_matrix(arr)
        dis = disassemble_sparse_matrix(mat)
        self.assertIsInstance(dis, dict)
        self.assertIn("shape", dis)
        self.assertIn("format", dis)
        self.assertIn("data", dis)
        self.assertEqual(dis["shape"], arr.shape)
        self.assertEqual(dis["format"], "csr")
        self.assertIsInstance(dis["data"], (tuple, list))
        self.assertEqual(len(dis["data"]), 3)
        self.assertTrue((dis["data"][0] == mat.data).all())
        self.assertTrue((dis["data"][1] == mat.indices).all())
        self.assertTrue((dis["data"][2] == mat.indptr).all())

    def test_assemble_sparse_matrix(self):
        tree = {
            "shape": (3, 10),
            "format": "csr",
            "data": [numpy.arange(1, 8),
                     numpy.array([0, 4, 1, 5, 2, 3, 8]),
                     numpy.array([0, 2, 4, 7])]
        }
        mat = assemble_sparse_matrix(tree)
        self.assertIsInstance(mat, csr_matrix)
        self.assertTrue((mat.data == tree["data"][0]).all())
        self.assertTrue((mat.indices == tree["data"][1]).all())
        self.assertTrue((mat.indptr == tree["data"][2]).all())
        self.assertEqual(mat.shape, (3, 10))
        self.assertEqual(mat.dtype, numpy.int)

    def test_pickle(self):
        docfreq = GenericModel(source=get_path(self.DOCFREQ_PATH))
        res = pickle.dumps(docfreq)
        docfreq_rec = pickle.loads(res)

        for k in docfreq.__dict__:
            self.assertEqual(docfreq.__dict__[k], docfreq_rec.__dict__[k])

    def test_write(self):
        meta = generate_meta("test", (1, 0, 3))
        with tempfile.NamedTemporaryFile() as tmp:
            write_model(meta, {"xxx": 100500}, tmp.name)
            with asdf.open(tmp.name) as f:
                self.assertEqual(f.tree["meta"]["model"], "test")
                self.assertEqual(f.tree["xxx"], 100500)
                self.assertEqual(oct(os.stat(tmp.name).st_mode)[-3:], "666")


if __name__ == "__main__":
    unittest.main()
