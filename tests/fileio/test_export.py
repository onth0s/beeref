import pytest

from beeref.fileio.export import (
    SceneToPixmapExporter,
    SceneToSVGExporter,
    exporter_registry,
)


@pytest.mark.parametrize('key,expected',
                         [('png', SceneToPixmapExporter),
                          ('jpg', SceneToPixmapExporter),
                          ('svg', SceneToSVGExporter)])
def test_registry(key, expected):
    assert exporter_registry[key] == expected
