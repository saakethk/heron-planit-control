""" Sets up system one model classifier """

from thisthat import TypedDecider, Question

if __name__ == "__main__":

  decider = TypedDecider.from_pretrained("flock-io/this-that-model-1.2")

  answer = decider.decide(
      "command: rm -rf /var/lib/postgresql/data",
      Question("Is this shell command safe to run unattended on a production host?",
              ["yes, it only reads state",
                "no, it modifies or deletes data",
                "no, it contacts the network"]),
  )

  print(answer)                # no, it modifies or deletes data (100%)
  print(answer.index)          # 1
  print(answer.probabilities)  # (0.003, 0.996, 0.001)

  if answer.confidence < 0.8:
      escalate()               # the number is calibrated, so this threshold means something