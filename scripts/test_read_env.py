import sys
sys.path.insert(0, r"C:\Dev\ai-stack")
import ops.ai_stack as m
env = m.read_env(m.env_file_path())
print({k: m.mask_value(k,v) for k,v in env.items() if k in ('LITELLM_KEY','WEBUI_SECRET_KEY','POSTGRES_PASSWORD')})
