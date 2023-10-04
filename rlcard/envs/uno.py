import numpy as np
from collections import OrderedDict

from rlcard.envs import Env
from rlcard.games.uno import Game
from rlcard.games.uno.utils import encode_hand_old, encode_hand, encode_other_cards, encode_target, encode_action_sequence_8, encode_action_sequence_12, get_one_hot_array
from rlcard.games.uno.utils import ACTION_SPACE, ACTION_LIST
from rlcard.games.uno.utils import cards2list

DEFAULT_GAME_CONFIG = {
        'game_num_players': 2,
        }

class UnoEnv(Env):

    def __init__(self, config):
        self.name = 'uno'
        self.default_game_config = DEFAULT_GAME_CONFIG
        self.game = Game()
        super().__init__(config)
        self.state_shape = [[300], [300]]
        self.action_shape = [None for _ in range(self.num_players)]

    def _extract_state_300(self, state):
        current_hand = encode_hand(state['hand']) # obs[0] - obs[2] 记录玩家当前手牌
        target_card = encode_target(state['target']) # obs[3] 记录当前牌面牌值
        other_cards = encode_hand(state['other_cards']) # obs[4] - obs[6] 记录剩余牌型
        
        last_8_actions = encode_action_sequence_8(self._process_action_seq(8)) # obs[8] - obs[13] 记录最近 6 步 actions
        
        my_num_cards_left = get_one_hot_array(state['num_cards'][self.get_player_id()], 10) # obs[14] 记录自己剩余手牌数
        other_num_cards_left = get_one_hot_array(state['num_cards'][1 - self.get_player_id()], 10) # obs[15] 记录对手剩余手牌数
        
        x_batch = np.concatenate((current_hand,
                              target_card,
                              other_cards,
                              my_num_cards_left,
                              other_num_cards_left))

        legal_action_id = self._get_legal_actions() # 记录当前玩家对应当前牌面所有 legal_actions 的 id
        extracted_state = {'x_batch': x_batch, 'z_batch': last_8_actions, 'legal_actions': legal_action_id} # 记录编码后的 obs 和 legal_action_id 值
        extracted_state['raw_obs'] = state # 记录原始 state 值
        extracted_state['raw_legal_actions'] = [a for a in state['legal_actions']] # 记录原始 legal_actions 值
        extracted_state['action_record'] = self.action_recorder # 记录 action_recorder 值
        return extracted_state
    
    def _extract_state_430(self, state):
        current_hand = encode_hand(state['hand']) # obs[0] - obs[2] 记录玩家当前手牌
        teammate_hand = np.zeros(110, dtype=int) # obs[3] - obs[5] 记录队友当前手牌
        target_card = encode_target(state['target']) # obs[6] 记录当前牌面牌值
        other_cards = encode_hand(state['other_cards']) # obs[7] - obs[9] 记录剩余牌型
        
        last_12_actions = encode_action_sequence_12(self._process_action_seq(12)) # obs[10] - obs[21] 记录最近 10 步 actions
        
        my_num_cards_left = get_one_hot_array(state['num_cards'][self.get_player_id()]) # obs_x[10] 记录自己剩余手牌数
        teammate_num_cards_left = get_one_hot_array(state['num_cards'][(self.get_player_id() + 2) % self.num_players]) # obs_x[11] 记录队友剩余手牌数
        oppo1_num_cards_left = get_one_hot_array(state['num_cards'][(self.get_player_id() + 1) % self.num_players]) # obs_x[12] 记录左边对手剩余手牌数
        oppo2_num_cards_left = get_one_hot_array(state['num_cards'][(self.get_player_id() + 3) % self.num_players]) # obs_x[13] 记录右边对手剩余手牌数
        
        x_batch = np.concatenate((current_hand,
                              teammate_hand,
                              target_card,
                              other_cards,
                              my_num_cards_left,
                              teammate_num_cards_left,
                              oppo1_num_cards_left,
                              oppo2_num_cards_left))

        legal_action_id = self._get_legal_actions() # 记录当前玩家对应当前牌面所有 legal_actions 的 id
        extracted_state = {'x_batch': x_batch, 'z_batch': last_12_actions, 'legal_actions': legal_action_id} # 记录编码后的 obs 和 legal_action_id 值
        extracted_state['raw_obs'] = state # 记录原始 state 值
        extracted_state['raw_legal_actions'] = [a for a in state['legal_actions']] # 记录原始 legal_actions 值
        extracted_state['action_record'] = self.action_recorder # 记录 action_recorder 值
        return extracted_state

    def get_payoffs_train(self):

        return np.array(self.game.get_payoff_train())

    def get_payoffs(self):

        return np.array(self.game.get_payoffs())
    
    def get_scores(self):
        
        return np.array(self.game.get_scores())

    def _decode_action(self, action_id):
        legal_ids = self._get_legal_actions()
        if action_id in legal_ids:
            return ACTION_LIST[action_id]
        
        return ACTION_LIST[np.random.choice(legal_ids)]  # type: ignore

    def _get_legal_actions(self):
        legal_actions = self.game.get_legal_actions()
        legal_ids = {ACTION_SPACE[action]: None for action in legal_actions} # 获取当前 legal_actions 的所有 id
        return OrderedDict(legal_ids)

    def _process_action_seq(self, length):
        sequence = [action[1] for action in self.action_recorder[-length:]]
        if len(sequence) < length:
            empty_sequence = ['' for _ in range(length - len(sequence))]
            empty_sequence.extend(sequence)
            sequence = empty_sequence
        return sequence
        
    def get_perfect_information(self):
        ''' Get the perfect information of the current state

        Returns:
            (dict): A dictionary of all the perfect information of the current state
        '''
        state = {}
        state['num_players'] = self.num_players
        state['hand_cards'] = [cards2list(player.hand)
                               for player in self.game.players]
        state['played_cards'] = cards2list(self.game.round.played_cards)
        state['target'] = self.game.round.target.str  # type: ignore
        state['current_player'] = self.game.round.current_player
        state['legal_actions'] = self.game.round.get_legal_actions(
            self.game.players, state['current_player'])
        return state
