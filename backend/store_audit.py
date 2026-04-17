import os
import sys
sys.path.append(os.getcwd())
from core.db import get_session
from core.models import Store

with get_session() as s:
    for st in s.query(Store).all():
        print(f"Name: {st.name} | Slug: {st.slug} | Logo: {st.logo_url}")
