"""Mermaid図のレンダリングユーティリティ"""

import streamlit.components.v1 as components


def render_mermaid(code: str, height: int = 500):
    """Mermaid図をダークモード対応でレンダリング"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
        <style>
            body {{
                background: transparent;
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: flex-start;
            }}
            .mermaid {{
                width: 100%;
            }}
            .mermaid svg {{
                width: 100% !important;
                max-height: {height - 20}px;
            }}
        </style>
    </head>
    <body>
        <pre class="mermaid">{code}</pre>
        <script>
            const isDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            mermaid.initialize({{
                startOnLoad: true,
                theme: isDark ? 'dark' : 'default',
                themeVariables: isDark ? {{
                    primaryColor: '#1e3a5f',
                    primaryTextColor: '#e0e0e0',
                    lineColor: '#4a9eff',
                    secondaryColor: '#2d2d2d',
                    tertiaryColor: '#1a1a2e',
                    fontSize: '18px',
                }} : {{
                    primaryColor: '#e8f4fd',
                    primaryTextColor: '#1a1a1a',
                    lineColor: '#0EA5E9',
                    fontSize: '18px',
                }},
                flowchart: {{ curve: 'basis', padding: 20, nodeSpacing: 50, rankSpacing: 60 }},
                fontSize: 18,
            }});
        </script>
    </body>
    </html>
    """
    components.html(html, height=height)


def estimate_mermaid_height(code: str, min_height: int = 300, max_height: int = 900) -> int:
    """Mermaidコードの行数から表示高さを推定"""
    lines = len([line for line in code.strip().split("\n") if line.strip()])
    estimated = 100 + lines * 35
    return max(min_height, min(estimated, max_height))
