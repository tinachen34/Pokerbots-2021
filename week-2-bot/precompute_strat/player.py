'''
Simple example pokerbot, written in Python.
'''
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction, AssignAction
from skeleton.states import GameState, TerminalState, RoundState, BoardState
from skeleton.states import NUM_ROUNDS, STARTING_STACK, BIG_BLIND, SMALL_BLIND, NUM_BOARDS
from skeleton.bot import Bot
from skeleton.runner import parse_args, run_bot

import eval7
import random
import pandas as pd 


class Player(Bot):
    '''
    A pokerbot.
    '''

    def __init__(self):
        '''
        Called when a new game starts. Called exactly once.

        Arguments:
        Nothing.

        Returns:
        Nothing.
        ''' 
        self.board_allocations = [[], [], []] #keep track of our allocations at round start
        self.hole_strengths = [0, 0, 0] #better representation of our hole strengths per round (win probability!)
        self.MONTE_CARLO_ITERS = 100 #the number of monte carlo samples we will use

        #make sure this df isn't too big!! Loading data all at once might be slow if you did more computations!
        calculated_df = pd.read_csv('hole_strengths.csv') #the values we computed offline, this df is slow to search through though
        holes = calculated_df.Holes #the columns of our spreadsheet
        strengths = calculated_df.Strengths
        self.starting_strengths = dict(zip(holes, strengths)) #convert to a dictionary, O(1) lookup time!

        self.opponent_moves = [[],[],[],]


    def rank_to_numeric(self, rank):
        '''
        Method that converts our given rank as a string
        into an integer ranking

        rank: str - one of 'A, K, Q, J, T, 9, 8, 7, 6, 5, 4, 3, 2'
        '''
        if rank.isnumeric(): #2-9, we can just use the int version of this string
            return int(rank)
        elif rank == 'T': #10 is T, so we need to specify it here
            return 10
        elif rank == 'J': #Face cards for the rest of them
            return 11
        elif rank == 'Q':
            return 12
        elif rank == 'K':
            return 13
        else: #Ace (A) is the only one left, give it the highest rank
            return 14


    def sort_cards_by_rank(self, cards):
        '''
        Method that takes in a list of cards in the engine's format
        and sorts them by rank order

        cards: list - a list of card strings in the engine's format (Kd, As, Th, 7d, etc.)
        '''
        return sorted(cards, reverse=True, key=lambda x: self.rank_to_numeric(x[0])) #we want it in descending order


    def hole_list_to_key(self, hole):
        '''
        Converts a hole card list into a key that we can use to query our 
        strength dictionary

        hole: list - A list of two card strings in the engine's format (Kd, As, Th, 7d, etc.)
        '''
        card_1 = hole[0] #get all of our relevant info
        card_2 = hole[1]

        rank_1, suit_1 = card_1[0], card_1[1] #card info
        rank_2, suit_2 = card_2[0], card_2[1]

        numeric_1, numeric_2 = self.rank_to_numeric(rank_1), self.rank_to_numeric(rank_2) #make numeric

        suited = suit_1 == suit_2 #off-suit or not
        suit_string = 's' if suited else 'o'

        if numeric_1 >= numeric_2: #keep our hole cards in rank order
            return rank_1 + rank_2 + suit_string
        else:
            return rank_2 + rank_1 + suit_string


    def allocate_cards(self, my_cards):
        '''
        Method that allocates our cards at the beginning of a round. Method
        modifies self.board_allocations. The method attempts to make pairs
        by allocating hole cards that share a rank if possible. The exact
        stack these cards are allocated to is not defined.

        Arguments:
        my_cards: a list of the 6 cards given to us at round start
        '''
        ranks = {}

        for card in my_cards:
            card_rank = card[0] #2 - 9, T, J, Q, K, A
            card_suit = card[1] # d, h, s, c

            if card_rank in ranks: #if we've seen this rank before, add the card to our list
                ranks[card_rank].append(card)

            else: #make a new list if we've never seen this one before
                ranks[card_rank] = [card]

        
        pairs = [] #keep track of all of the pairs we identified
        singles = [] #all other cards

        for rank in ranks:
            cards = ranks[rank]

            if len(cards) == 1: #single card, can't be in a pair
                singles.append(cards[0])
            
            elif len(cards) == 2 or len(cards) == 4: #a single pair or two pairs can be made here, add them all
                pairs += cards
            
            else: #len(cards) == 3  A single pair plus an extra can be made here
                pairs.append(cards[0])
                pairs.append(cards[1])
                singles.append(cards[2])

        cards_remaining = set(my_cards) #keep track of the cards we need to allocate still
        allocated_cards = set() #the cards we've committed to the board
        holes_allocated = [] #the holes we've made

        _MIN_PAIR_VALUE = 5 #we only want pairs stronger than this!

        for i in range(len(pairs) // 2):
            pair = [pairs[2*i], pairs[2*i + 1]] #get our pair
            pair_rank = pair[0][0] 

            if self.rank_to_numeric(pair_rank) >= _MIN_PAIR_VALUE: #our pair is strong! keep it!
                holes_allocated.append(pair)
                allocated_cards.update(pair)
        
        cards_remaining = cards_remaining - allocated_cards #update our remaining cards

        sorted_remaining = self.sort_cards_by_rank(list(cards_remaining)) #sort our remaining cards

        for i in range(len(sorted_remaining) - 1): #go through every adjecent card for straight draws!
            card_1 = sorted_remaining[i]
            card_2 = sorted_remaining[i + 1]

            rank_diff = self.rank_to_numeric(card_1[0]) - self.rank_to_numeric(card_2[0]) #how far apart our ranks are

            if (rank_diff <= 1) and (card_1 not in allocated_cards) and (card_2 not in allocated_cards): #if they're close and unused
                hole = [card_1, card_2] #use them!
                holes_allocated.append(hole)
                allocated_cards.update(hole)
        
        cards_remaining = cards_remaining - allocated_cards #update our bookkeeping

        suits = {}
        for card in cards_remaining: #look for flush draws
            card_suit = card[1]

            if card_suit in suits:
                suits[card_suit].append(card)
            
            else:
                suits[card_suit] = [card]
        

        for suit in suits:

            cards = suits[suit]
            if len(cards) == 2 or len(cards) == 3: #we found something!
                hole = [cards[0], cards[1]]
                holes_allocated.append(hole)
                allocated_cards.update(hole)

            elif len(cards) == 4: #be wary!!! this could be too many of the same suits
                hole_1 = [cards[0], cards[1]] #but we'll try anyway for now
                hole_2 = [cards[2], cards[3]]

                holes_allocated.append(hole_1)
                allocated_cards.update(hole_1)

                holes_allocated.append(hole_2)
                allocated_cards.update(hole_2)

        cards_remaining = cards_remaining - allocated_cards #update cards remaining
        extra_cards = list(cards_remaining)

        for i in range(len(extra_cards) // 2): #we couldnt do anything with these...oh well
            hole = [extra_cards[2*i], extra_cards[2*i + 1]] #just group them up randomly
            holes_allocated.append(hole)
            allocated_cards.update(hole)

        cards_remaining = cards_remaining - allocated_cards #final update

        assert len(holes_allocated) == 3, 'we allocated too many cards!!' #check for mistakes!!!
        assert len(cards_remaining) == 0, "we didn't allocate enough!"

        return holes_allocated #return our decisions


    def assign_holes(self, hole_cards):
        '''
        A method that assigns the created hole cards to particular boards

        hole_cards: list - a list of lists, where each list is a hole card pair in the
                    engine's format
        '''

        holes_and_strengths = [] #keep track of holes and their strengths

        for hole in hole_cards:
            key = self.hole_list_to_key(hole)
            strength = self.starting_strengths[key]
            holes_and_strengths.append((hole, strength))
        
        holes_and_strengths = sorted(holes_and_strengths, key=lambda x: x[1]) #sort them by strength

        if random.random() < 0.1: #swap strongest with second, makes our strategy non-deterministic!
            temp = holes_and_strengths[2]
            holes_and_strengths[2] = holes_and_strengths[1]
            holes_and_strengths[1] = temp
        
        if random.random() < 0.1: #swap second with last, makes us even more random
            temp = holes_and_strengths[1]
            holes_and_strengths[1] = holes_and_strengths[0]
            holes_and_strengths[0] = temp
        
        for i in range(NUM_BOARDS): #we have our final board allocations!
            self.board_allocations[i] = holes_and_strengths[i][0]
            self.hole_strengths[i] = holes_and_strengths[i][1]


    def handle_new_round(self, game_state, round_state, active):
        '''
        Called when a new round starts. Called NUM_ROUNDS times.

        Arguments:
        game_state: the GameState object.
        round_state: the RoundState object.
        active: your player's index.

        Returns:
        Nothing.
        '''
        my_bankroll = game_state.bankroll  # the total number of chips you've gained or lost from the beginning of the game to the start of this round
        opp_bankroll = game_state.opp_bankroll # ^but for your opponent
        game_clock = game_state.game_clock  # the total number of seconds your bot has left to play this game
        round_num = game_state.round_num  # the round number from 1 to NUM_ROUNDS
        my_cards = round_state.hands[active]  # your six cards at the start of the round
        big_blind = bool(active)  # True if you are the big blind

        
        allocated_holes = self.allocate_cards(my_cards) #our allocation strategy
        self.assign_holes(allocated_holes) #our randomized assignment method


    def handle_round_over(self, game_state, terminal_state, active):
        '''
        Called when a round ends. Called NUM_ROUNDS times.

        Arguments:
        game_state: the GameState object.
        terminal_state: the TerminalState object.
        active: your player's index.

        Returns:
        Nothing.
        '''
        my_delta = terminal_state.deltas[active]  # your bankroll change from this round
        opp_delta = terminal_state.deltas[1-active] # your opponent's bankroll change from this round 
        previous_state = terminal_state.previous_state  # RoundState before payoffs
        street = previous_state.street  # 0, 3, 4, or 5 representing when this round ended
        for terminal_board_state in previous_state.board_states:
            previous_board_state = terminal_board_state.previous_state
            my_cards = previous_board_state.hands[active]  # your cards
            opp_cards = previous_board_state.hands[1-active]  # opponent's cards or [] if not revealed
        
        self.board_allocations = [[], [], []] #reset our variables at the end of every round!
        self.hole_strengths = [0, 0, 0]
        self.last_seen_street = 0

        game_clock = game_state.game_clock #check how much time we have remaining at the end of a game
        round_num = game_state.round_num #Monte Carlo takes a lot of time, we use this to adjust!
        if round_num == NUM_ROUNDS:
            print(game_clock)
        

    def get_actions(self, game_state, round_state, active):
        '''
        Where the magic happens - your code should implement this function.
        Called any time the engine needs a triplet of actions from your bot.

        Arguments:
        game_state: the GameState object.
        round_state: the RoundState object.
        active: your player's index.

        Returns:
        Your actions.
        '''
        legal_actions = round_state.legal_actions()  # the actions you are allowed to take
        street = round_state.street  # 0, 3, 4, or 5 representing pre-flop, flop, turn, or river respectively
        my_cards = round_state.hands[active]  # your cards across all boards
        board_cards = [board_state.deck if isinstance(board_state, BoardState) else board_state.previous_state.deck for board_state in round_state.board_states] #the board cards
        my_pips = [board_state.pips[active] if isinstance(board_state, BoardState) else 0 for board_state in round_state.board_states] # the number of chips you have contributed to the pot on each board this round of betting
        opp_pips = [board_state.pips[1-active] if isinstance(board_state, BoardState) else 0 for board_state in round_state.board_states] # the number of chips your opponent has contributed to the pot on each board this round of betting
        continue_cost = [opp_pips[i] - my_pips[i] for i in range(NUM_BOARDS)] #the number of chips needed to stay in each board's pot
        my_stack = round_state.stacks[active]  # the number of chips you have remaining
        opp_stack = round_state.stacks[1-active]  # the number of chips your opponent has remaining
        stacks = [my_stack, opp_stack]
        net_upper_raise_bound = round_state.raise_bounds()[1] # max raise across 3 boards
        net_cost = 0 # keep track of the net additional amount you are spending across boards this round

        my_actions = [None] * NUM_BOARDS
        for i in range(NUM_BOARDS):
            if AssignAction in legal_actions[i]:
                cards = self.board_allocations[i] #assign our cards that we made earlier
                my_actions[i] = AssignAction(cards) #add to our actions

            elif isinstance(round_state.board_states[i], TerminalState): #make sure the game isn't over at this board
                my_actions[i] = CheckAction() #check if it is
            
            else: #do we add more resources?
                board_cont_cost = continue_cost[i] #we need to pay this to keep playing
                board_total = round_state.board_states[i].pot #amount before we started betting
                pot_total = my_pips[i] + opp_pips[i] + board_total #total money in the pot right now
                min_raise, max_raise = round_state.board_states[i].raise_bounds(active, round_state.stacks)
                strength = self.hole_strengths[i]

                #ME TRYING SOME STUFF: keeping track of opponent's moves
                if board_cont_cost > 0:
                    self.opponent_moves[i].append(RaiseAction)
                else:
                    self.opponent_moves[i].append(None)

                if street < 3: #pre-flop
                    raise_ammount = int(my_pips[i] + board_cont_cost + 0.25 * (pot_total + board_cont_cost)) #play a little conservatively pre-flop
                else:
                    raise_ammount = int(my_pips[i] + board_cont_cost + 0.85 * (pot_total + board_cont_cost)) #raise the stakes deeper into the game
                
                raise_ammount = max([min_raise, raise_ammount]) #make sure we have a valid raise
                raise_ammount = min([max_raise, raise_ammount])

                raise_cost = raise_ammount - my_pips[i] #how much it costs to make that raise

                if RaiseAction in legal_actions[i] and (raise_cost <= my_stack - net_cost): #raise if we can and if we can afford it
                    commit_action = RaiseAction(raise_ammount)
                    commit_cost = raise_cost
                
                elif CallAction in legal_actions[i] and (board_cont_cost <= my_stack - net_cost): #call if we can afford it!
                    commit_action = CallAction()
                    commit_cost = board_cont_cost #the cost to call is board_cont_cost
                
                elif CheckAction in legal_actions[i]: #try to check if we can
                    commit_action = CheckAction()
                    commit_cost = 0
                
                else: #we have to fold 
                    commit_action = FoldAction()
                    commit_cost = 0


                if board_cont_cost > 0: #our opp raised!!! we must respond

                    #ME TRYING STUFF: if they raise 2+ times, then be careful
                    if self.opponent_moves.count(RaiseAction) >= 2:
                        _INTIMIDATION = 0.1
                        strength = max([0, strength - _INTIMIDATION]) #if our opp raises a lot, be cautious!
                    
                    if board_cont_cost > 5: #<--- parameters to tweak. 
                        _INTIMIDATION = 0.15
                        strength = max([0, strength - _INTIMIDATION]) #if our opp raises a lot, be cautious!
                    

                    pot_odds = board_cont_cost / (pot_total + board_cont_cost)

                    if strength >= pot_odds: #Positive Expected Value!! at least call!!

                        if strength > 0.5 and random.random() < strength: #raise sometimes, more likely if our hand is strong
                            my_actions[i] = commit_action
                            net_cost += commit_cost
                        
                        else: # try to call if we don't raise
                            if (board_cont_cost <= my_stack - net_cost): #we call because we can afford it and it's +EV
                                my_actions[i] = CallAction()
                                net_cost += board_cont_cost
                                
                            else: #we can't afford to call :(  should have managed our stack better
                                my_actions[i] = FoldAction()
                                net_cost += 0
                    
                    else: #Negative Expected Value!!! FOLD!!!
                        my_actions[i] = FoldAction()
                        net_cost += 0
                
                else: #board_cont_cost == 0, we control the action

                    if random.random() < strength: #raise sometimes, more likely if our hand is strong
                        my_actions[i] = commit_action
                        net_cost += commit_cost

                    else: #just check otherwise
                        my_actions[i] = CheckAction()
                        net_cost += 0

        return my_actions


if __name__ == '__main__':
    run_bot(Player(), parse_args())
