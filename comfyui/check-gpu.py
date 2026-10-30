"""Fail before activation if the wheel/runtime cannot actually execute on Pascal."""

import torch
import torch.nn.functional as functional


def main():
    if not torch.cuda.is_available():
        raise SystemExit("PyTorch cannot access the NVIDIA GPU")
    if torch.version.cuda != "12.6":
        raise SystemExit(f"Expected CUDA 12.6, found {torch.version.cuda}")

    capability = torch.cuda.get_device_capability()
    if capability != (6, 1):
        raise SystemExit(f"Expected Pascal sm_61, found {capability}")
    architectures = torch.cuda.get_arch_list()
    # sm_60 cubins are forward-compatible with the GTX 1080's sm_61.
    if not {"sm_60", "sm_61"}.intersection(architectures):
        raise SystemExit(f"Installed PyTorch lacks Pascal support: {architectures}")

    cudnn = torch.backends.cudnn.version()
    if cudnn != 91002:
        raise SystemExit(f"Expected Pascal-compatible cuDNN 9.10.2, found {cudnn}")

    with torch.inference_mode():
        if (torch.ones(1, device="cuda") * 2).item() != 2:
            raise SystemExit("CUDA arithmetic failed")

        image = torch.arange(4 * 16 * 16, dtype=torch.float32).reshape(1, 4, 16, 16) / 1024
        weight = torch.ones(4, 4, 3, 3, dtype=torch.float32) / 36
        expected = functional.conv2d(image, weight, padding=1)
        # Call cuDNN explicitly: ordinary conv2d can silently use another backend.
        actual = torch.ops.aten.cudnn_convolution(
            image.cuda(), weight.cuda(), [1, 1], [1, 1], [1, 1], 1, False, True, False
        )
        torch.cuda.synchronize()
        torch.testing.assert_close(actual.cpu(), expected, rtol=1e-4, atol=1e-4)

    print(
        f"CUDA + cuDNN convolution passed: {torch.cuda.get_device_name(0)} "
        f"(torch {torch.__version__}, CUDA {torch.version.cuda}, cuDNN {cudnn})"
    )


if __name__ == "__main__":
    main()
