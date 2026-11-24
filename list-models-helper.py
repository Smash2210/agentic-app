from dotenv import load_dotenv; 
load_dotenv(); 
from google import genai; 
c = genai.Client(); 
[print(m.name) for m in c.models.list()]