import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
})

type RenderRule = NonNullable<typeof md.renderer.rules.link_open>

const defaultLinkOpen: RenderRule = md.renderer.rules.link_open
  || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  tokens[idx].attrSet('target', '_blank')
  tokens[idx].attrSet('rel', 'noopener noreferrer')
  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(text: string): string {
  // 后端模型偶尔会把标题写在句子中间，补一个换行让 Markdown 正确分块。
  const normalized = text
    .replace(/^(#{1,6})([^\s#])/gm, '$1 $2')
    .replace(/([。；;])(#{1,6})([^\s#])/g, '$1\n$2 $3')
  return md.render(normalized)
}
