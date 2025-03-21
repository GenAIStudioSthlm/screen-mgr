import json
from typing import List
from pydantic import BaseModel, Field, ValidationError
from fastapi import WebSocket

# File to store screen URLs
SCREENS_FILE = "screens.json"


class Screen(BaseModel):
    id: int = Field(..., description="Unique identifier for the screen")
    name: str = Field(..., description="Name of the screen")
    type: str = Field(
        ...,
        pattern="^(text|url|default|video|picture)$",
        description="Type of the screen content, either 'text' or 'url'",
    )
    text: str = Field("", description="Text content for the screen")
    url: str = Field("", description="URL content for the screen")
    video: str = Field("", description="Video content for the screen (if applicable)")
    picture: str = Field(
        "", description="Picture content for the screen (if applicable)"
    )
    connected: bool = Field(
        False,
        description="Indicates if the screen is currently connected",
    )
    websocket: WebSocket = Field(
        None,
        description="WebSocket connection for the screen",
    )

    class Config:
        arbitrary_types_allowed = True


class ScreenManager:
    def __init__(self):
        self.screens: List[Screen] = []

    # Load screens from file
    def load_screens(self) -> List[Screen]:
        try:
            with open(SCREENS_FILE, "r", encoding="utf-8") as file:
                raw_screens = json.load(file)
                self.screens = [Screen(**screen) for screen in raw_screens]
                # print(str(self.screens))

        except FileNotFoundError:
            self.screens = [
                Screen(id=1, name="Station 1", type="default"),
                Screen(id=2, name="Station 2", type="default"),
                Screen(id=3, name="Station 3", type="default"),
                Screen(id=4, name="Screen 2", type="default"),
                Screen(id=5, name="Screen 3", type="default"),
                Screen(id=6, name="Main Screen", type="default"),
            ]
        except ValidationError as e:
            print(f"Error loading screens: {e}")

        # Print screens
        print("Loaded screens:")
        for screen in self.screens:
            print(screen.model_dump())

    # Save screens to file
    def save_screens(self):
        with open(SCREENS_FILE, "w", encoding="utf-8") as file:
            json.dump(
                [
                    {
                        key: value
                        for key, value in screen.model_dump().items()
                        if key not in {"websocket", "connected"}
                    }
                    for screen in self.screens
                ],
                file,
                indent=4,
            )

    def print_screens(self):
        print("Current screen data:")
        for screen in self.screens:
            print(screen.model_dump(exclude={"websocket"}))


screen_manager = ScreenManager()
screen_manager.load_screens()
