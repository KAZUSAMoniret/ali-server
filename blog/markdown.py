import nh3
from markdown_it import MarkdownIt

parser = MarkdownIt('commonmark', {'html': False, 'breaks': True}).enable('table')

def render_markdown(text):
    return nh3.clean(parser.render(text or ''),
                     tags={'p', 'br', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'a', 'img',
                           'blockquote', 'ul', 'ol', 'li', 'pre', 'code', 'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td'},
                     attributes={'a': {'href', 'title'}, 'img': {'src', 'alt', 'title'}, 'code': {'class'}, 'ol': {'start'}},
                     url_schemes={'http', 'https', 'mailto'})
