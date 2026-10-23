-- 본문의 [확인] [해석] [가설] [미확인]을 색깔 배지로 바꾼다.
local TAGS = {
  { "[확인]", "확인", "tag-fact" },
  { "[해석]", "해석", "tag-interp" },
  { "[가설]", "가설", "tag-hypo" },
  { "[미확인]", "미확인", "tag-unverified" },
}

function Str(el)
  for _, t in ipairs(TAGS) do
    local s, e = el.text:find(t[1], 1, true)
    if s then
      local out = {}
      local before = el.text:sub(1, s - 1)
      local after = el.text:sub(e + 1)
      if #before > 0 then table.insert(out, pandoc.Str(before)) end
      table.insert(out, pandoc.Span({ pandoc.Str(t[2]) }, { class = "tag " .. t[3] }))
      if #after > 0 then table.insert(out, pandoc.Str(after)) end
      return out
    end
  end
end
