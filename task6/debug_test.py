import time
import sys
from pathlib import Path
from synthesize import synthesize_enhanced

# Ensure the task6 directory is in sys.path to import the correct schemas
TASK6_DIR = Path(__file__).parent
if str(TASK6_DIR) not in sys.path:
    sys.path.insert(0, str(TASK6_DIR))
from ollama_llm import OllamaLLMClient
from mock_data import easy_case

print('Debugging structured actions issue...')
llm_client = OllamaLLMClient()
anomaly, correlation, evidence = easy_case()

# Get the original story first
from synthesize import synthesize
story = synthesize(anomaly, correlation, evidence, llm_client)
print('Original story:')
print('  Headline:', story.headline)
print('  Confidence:', story.overall_confidence)
print('  Escalate:', story.escalate_flag)
print('  Number of hypotheses:', len(story.hypotheses))
for i, h in enumerate(story.hypotheses):
    print('    Hypothesis {}: {}'.format(i+1, h.cause))
    print('      Confidence: {}'.format(h.confidence))
    print('      Citations: {}'.format(h.citations))
    print('      Actions: {}'.format(h.actions))

# Now test the action enhancer
from action_enhancer import ActionEnhancer
enhancer = ActionEnhancer()
print('\\nTesting action enhancer...')
structured_actions = enhancer.enhance_actions(story.hypotheses, correlation, evidence, anomaly)
print('Number of structured actions from enhancer:', len(structured_actions))
for i, action in enumerate(structured_actions):
    print('  Action {}:'.format(i+1))
    print('    Driver: {}'.format(action.driver))
    print('    Leverage: {}'.format(action.controllable_leverage))
    print('    Action: {}'.format(action.action))
    print('    Impact: {}'.format(action.expected_impact))
    print('    Owner: {}'.format(action.owner))
    print('    Confidence: {}'.format(action.confidence))
    print('    Monitoring: {}'.format(action.monitoring_plan))

# Now run the full enhanced synthesis
print('\\nRunning full enhanced synthesis...')
start = time.time()
result = synthesize_enhanced(anomaly, correlation, evidence, llm_client)
end = time.time()
print('Full synthesis took {:.2f} seconds'.format(end - start))
print('\\nResults from synthesize_enhanced:')
print('  Headline:', result['original_story'].headline)
print('  Number of structured actions:', len(result['structured_actions']))
print('  Number of persona narratives:', len(result['persona_narratives']))
