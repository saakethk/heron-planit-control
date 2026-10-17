""" Sets up system one model classifier """

from transformers import AutoTokenizer, AutoModelForCausalLM

if __name__ == "__main__":
  tokenizer = AutoTokenizer.from_pretrained("flock-io/this-that-model-1.0")
  model = AutoModelForCausalLM.from_pretrained(
      "flock-io/this-that-model-1.0", 
      device_map="auto"
  )