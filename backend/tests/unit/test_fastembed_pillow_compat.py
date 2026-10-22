"""The supported image dependency graph retains FastEmbed preprocessing behavior."""

import numpy as np
import pytest
from packaging.version import Version
from PIL import Image


def test_image_dependency_is_on_the_security_fixed_major() -> None:
    assert Version(Image.__version__) >= Version("13.0.0")


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "L"])
def test_fastembed_image_preprocessing_preserves_rgb_tensor(mode: str) -> None:
    from fastembed.image.transform.operators import Compose

    source = Image.new("RGB", (12, 8), (64, 64, 64)).convert(mode)
    processor = Compose.from_config(
        {
            "do_resize": True,
            "size": {"height": 16, "width": 16},
            "do_rescale": True,
            "rescale_factor": 1 / 255,
            "do_normalize": True,
            "image_mean": [0.5, 0.5, 0.5],
            "image_std": [0.5, 0.5, 0.5],
        }
    )
    tensor = np.asarray(processor([source]))
    assert tensor.shape == (1, 3, 16, 16)
    assert np.isfinite(tensor).all()
    assert np.allclose(tensor, -0.498039215686, atol=1e-6)


@pytest.mark.parametrize("dtype", [np.uint8, np.float32])
def test_fastembed_tensor_resize_uses_supported_pillow_types(dtype) -> None:
    from fastembed.image.transform.functional import resize_ndarray

    source = np.full((3, 8, 12), 64 if dtype == np.uint8 else 0.25, dtype=dtype)
    resized = resize_ndarray(source, (16, 16))
    assert resized.shape == (3, 16, 16)
    assert np.isfinite(resized).all()
    expected = 64 if dtype == np.uint8 else 0.247058823529
    assert np.allclose(resized, expected, atol=1e-6)
