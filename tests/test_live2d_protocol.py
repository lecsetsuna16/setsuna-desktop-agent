import json
import unittest
from resona_desktop_pet.live2d.protocol import validate_perform, validate_sing, tool_definitions


class Live2DProtocolTests(unittest.TestCase):
    def test_valid_partial_command_uses_defaults(self):
        payload = validate_perform({'motion':'nod'})
        self.assertEqual(payload, {'expression':'neutral','motion':'nod','look':'center','intensity':.6,'hold_ms':1800})

    def test_unsupported_or_nonfinite_commands_rejected(self):
        for invalid in ({'motion':'wave'},{'expression':'blush'},{'look':'behind'}, {'intensity':float('nan')},
                        {'intensity':float('inf')},{'intensity':-1},{'intensity':True},{'hold_ms':False},
                        {'hold_ms':9000},{'hold_ms':1.2},{'ParamAngleX':30},{'_error':'bad JSON'}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_perform(invalid)

    def test_schema_and_validator_agree(self):
        function = next(t['function'] for t in tool_definitions() if t['function']['name'] == 'setsuna_perform')
        parameters = function['parameters']
        self.assertFalse(parameters['additionalProperties'])
        for field in ('expression','motion','look'):
            for value in parameters['properties'][field]['enum']:
                self.assertEqual(validate_perform({field:value})[field],value)

    def test_tools_are_json_serializable_without_raw_parameter_access(self):
        tools = json.loads(json.dumps(tool_definitions(), allow_nan=False))
        self.assertEqual({t['function']['name'] for t in tools}, {'setsuna_local_music','setsuna_sing','setsuna_perform','setsuna_status','setsuna_reset'})
        self.assertNotIn('set_parameter',str(tools))

    def test_sing_defaults_and_invalid_inputs(self):
        self.assertEqual(validate_sing({}), {'command': 'start', 'duration_seconds': 16.0})
        self.assertEqual(validate_sing({'command': 'stop'})['command'], 'stop')
        for bad in ({'duration_seconds': True}, {'duration_seconds': 0}, {'duration_seconds': 301},
                    {'duration_seconds': float('nan')}, {'command': 'hug'}, {'ParamArmAction': 2.5}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_sing(bad)


if __name__ == '__main__':
    unittest.main()
