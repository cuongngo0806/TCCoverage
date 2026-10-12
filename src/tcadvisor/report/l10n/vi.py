"""Vietnamese catalog: the union of the ``vi_*`` modules' ``ENTRIES``.

Style guide (keep every module consistent):

* Short, imperative, plain Vietnamese with full diacritics, as an embedded C++ test engineer would write it
  ("Kiểm tra ...", "Xác nhận ...", "Chạy lại ..."). One English sentence -> one Vietnamese sentence.
* Keep these engineering terms in English (Vietnamese teams use them as is): test case, corner case, test,
  caller, callee, target (the device / CMake target), build, commit, diff, macro, template, header, struct, class,
  enum, typedef, namespace, API, ABI, layout, thread, mutex, lock, race, deadlock, callback, handler, buffer,
  overflow, pointer, null, nullptr, iterator, exception, timeout, flag, config, option, RTOS, ISR, interrupt,
  hop, mock, stub, review, regression, side effect, cache, index, graph, codegraph, GitNexus, libclang,
  CMake, compile database, gtest, P1/P2/P3.
* Translate: function -> hàm, method -> phương thức, variable -> biến, member -> thành viên, field -> trường,
  parameter -> tham số, argument -> đối số, return value -> giá trị trả về, caller of X -> caller của X,
  changed -> bị thay đổi / đã thay đổi, removed -> bị xoá, added -> được thêm, guard -> điều kiện chặn (guard),
  boundary -> biên, state -> trạng thái, reader -> nơi đọc, writer -> nơi ghi, path -> đường đi,
  source -> nguồn, evidence -> bằng chứng, uncertain -> chưa chắc chắn, review manually -> cần review thủ công,
  verify / check -> kiểm tra, behaviour -> hành vi, value -> giá trị, error -> lỗi, warning -> cảnh báo,
  run notes -> ghi chú lần chạy, impact -> ảnh hưởng (impact), dependents -> các phần phụ thuộc.
* Never translate what is inside backticks, symbol / file names, numbers, regexes or command lines: they are
  placeholders ({name}). A literal brace in a translation must be doubled ({{ / }}).
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path


def entries() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    pkg = Path(__file__).parent
    for mod in sorted(m.name for m in pkgutil.iter_modules([str(pkg)]) if m.name.startswith("vi_")):
        out.extend(importlib.import_module(f"tcadvisor.report.l10n.{mod}").ENTRIES)
    return out
