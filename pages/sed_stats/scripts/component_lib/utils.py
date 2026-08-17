"""
Utility functions for component library.

Provides helper functions for animations, styling, and common component patterns.
"""
from typing import Dict, Any


def inject_keyframes(keyframe_id: str, keyframes_dict: Dict[str, Dict[str, Any]]):
    """
    Inject CSS keyframes into the document in a Pythonic way.

    Args:
        keyframe_id: Unique ID for the style element
        keyframes_dict: Dictionary of animation definitions
            Format: {
                'animation-name': {
                    '0%': {'property': 'value', ...},
                    '100%': {'property': 'value', ...}
                }
            }

    Example:
        inject_keyframes('my-spin-animation', {
            'spin': {
                '0%': {'transform': 'rotate(0deg)'},
                '100%': {'transform': 'rotate(360deg)'}
            }
        })
    """
    from js import document

    # Check if already injected
    if document.getElementById(keyframe_id):
        return

    # Convert keyframes dict to CSS
    css_rules = []
    for animation_name, frames in keyframes_dict.items():
        frame_rules = []
        for selector, properties in frames.items():
            prop_list = [f"    {key.replace('_', '-')}: {value};" for key, value in properties.items()]
            frame_rules.append(f"  {selector} {{\n" + "\n".join(prop_list) + "\n  }")

        css_rules.append(f"@keyframes {animation_name} {{\n" + "\n".join(frame_rules) + "\n}")

    css_content = "\n\n".join(css_rules)

    # Create and inject style element
    style = document.createElement('style')
    style.id = keyframe_id
    style.textContent = css_content
    document.head.appendChild(style)