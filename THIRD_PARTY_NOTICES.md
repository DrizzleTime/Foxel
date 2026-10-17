# Third-Party Notices

## PikPak Upload Protocol

`domain/adapters/providers/pikpak.py` adapts the GCID and OSS multipart
upload protocol from [Bengerthelorf/pikpaktui](https://github.com/Bengerthelorf/pikpaktui),
`src/pikpak/upload.rs` at commit `81d7621c66a6f747b60618a4bf8b336476071e66`.
The upload completion checks in `domain/adapters/providers/pikpak.py` also refer
to `src/pikpak/mutation.rs` from the same project.

Copyright 2025 Bengerthelorf

Licensed under the Apache License, Version 2.0. The complete upstream license is
included in [licenses/pikpaktui-Apache-2.0.txt](licenses/pikpaktui-Apache-2.0.txt).
The Foxel implementation uses Python async file objects and HTTPX, adds bounded
streaming, retry and abort handling, and integrates with Foxel's adapter API.
`tests/test_pikpak_upload.py` also includes the upstream GCID compatibility
vectors, which were obtained from the official web WASM.

## 115 Download Wire Format

`domain/adapters/providers/_115_cipher.py` adapts the m115 protocol implementation
from https://github.com/SheltonZhu/115driver/tree/main/pkg/crypto/m115.

MIT License

Copyright (c) 2022-2024 SheltonZhu

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
