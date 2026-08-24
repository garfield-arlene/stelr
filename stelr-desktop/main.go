package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/widget"
)

type Link struct {
	ID      string `json:"id"`
	Title   string `json:"title"`
	URL     string `json:"url"`
	Rank    int    `json:"rank"`
	GroupID string `json:"group_id"`
}

func getLinks(serverURL, apiToken, search string) ([]Link, error) {
	baseURL := strings.TrimRight(serverURL, "/") + "/api/links"

	if search != "" {
		baseURL += "?q=" + url.QueryEscape(search)
	}

	req, err := http.NewRequest("GET", baseURL, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", "Bearer "+apiToken)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to get links: %s", resp.Status)
	}

	var links []Link

	err = json.NewDecoder(resp.Body).Decode(&links)
	if err != nil {
		return nil, err
	}

	return links, nil
}

func login(serverURL, username, password string) (string, error) {
	data := map[string]string{
		"username": username,
		"password": password,
		"name":     "stelr-desktop",
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return "", err
	}

	url := strings.TrimRight(serverURL, "/") + "/api/tokens"

	resp, err := http.Post(
		url,
		"application/json",
		bytes.NewBuffer(jsonData),
	)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		return "", fmt.Errorf("Login failed: %s", resp.Status)
	}

	var result struct {
		Token string `json:"token"`
	}

	err = json.NewDecoder(resp.Body).Decode(&result)
	if err != nil {
		return "", err
	}

	return result.Token, nil
}

func addLink(serverURL, apiToken, title, linkURL string, rank int) error {
	data := map[string]any{
		"title": title,
		"url":   linkURL,
		"rank":  rank,
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return err
	}

	url := strings.TrimRight(serverURL, "/") + "/api/links"

	req, err := http.NewRequest(
		"POST",
		url,
		bytes.NewBuffer(jsonData),
	)

	if err != nil {
		return err
	}

	req.Header.Set("Authorization", "Bearer "+apiToken)
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		return fmt.Errorf("could not add link: %s", resp.Status)
	}

	return nil
}

func deleteLink(serverURL, apiToken, linkID string) error {
	url := strings.TrimRight(serverURL, "/") + "/api/links/" + linkID

	req, err := http.NewRequest("DELETE", url, nil)
	if err != nil {
		return err
	}

	req.Header.Set("Authorization", "Bearer "+apiToken)

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK &&
		resp.StatusCode != http.StatusNoContent {
		return fmt.Errorf("delete failed: %s", resp.Status)
	}

	return nil
}

func updateLink(serverURL, apiToken, linkID, title, linkURL string, rank int) error {
	data := map[string]any{
		"title": title,
		"url":   linkURL,
		"rank":  rank,
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return err
	}

	url := strings.TrimRight(serverURL, "/") + "/api/links/" + linkID

	req, err := http.NewRequest(
		"PUT",
		url,
		bytes.NewBuffer(jsonData),
	)
	if err != nil {
		return err
	}

	req.Header.Set("Authorization", "Bearer "+apiToken)
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return fmt.Errorf("Update failed: %s", resp.Status)
	}

	return nil
}

func main() {

	selectedID := -1

	myApp := app.New()
	window := myApp.NewWindow("Stelr Desktop")

	serverEntry := widget.NewEntry()
	serverEntry.SetPlaceHolder("http://localhost:8082")

	usernameEntry := widget.NewEntry()
	usernameEntry.SetPlaceHolder("bobo")

	passwordEntry := widget.NewPasswordEntry()
	passwordEntry.SetPlaceHolder("password")

	statusLabel := widget.NewLabel("")

	var links []Link
	var apiToken string

	titleEntry := widget.NewEntry()
	titleEntry.SetPlaceHolder("GitHub")

	urlEntry := widget.NewEntry()
	urlEntry.SetPlaceHolder("https://github.com")

	rankEntry := widget.NewEntry()
	rankEntry.SetPlaceHolder("1")

	searchEntry := widget.NewEntry()
	searchEntry.SetPlaceHolder("Search bookmarks...")

	linkList := widget.NewList(
		func() int {
			return len(links)
		},
		func() fyne.CanvasObject {
			return widget.NewLabel("")
		},
		func(id widget.ListItemID, obj fyne.CanvasObject) {
			label := obj.(*widget.Label)

			link := links[id]

			label.SetText(
				fmt.Sprintf("%d - %s - %s",
					link.Rank,
					link.Title,
					link.URL),
			)
		},
	)

	linkList.OnSelected = func(id widget.ListItemID) {
		selectedID = int(id)

		link := links[id]

		titleEntry.SetText(link.Title)
		urlEntry.SetText(link.URL)
		rankEntry.SetText(strconv.Itoa(link.Rank))

		statusLabel.SetText("Selected: " + link.Title)
	}

	searchButton := widget.NewButton("Search", func() {
		if apiToken == "" {
			statusLabel.SetText("Connect first")
			return
		}

		search := searchEntry.Text
		serverURL := serverEntry.Text

		go func() {
			newLinks, err := getLinks(serverURL, apiToken, search)
			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText("Search failed: " + err.Error())
				})
				return
			}

			fyne.Do(func() {
				links = newLinks
				selectedID = -1

				linkList.UnselectAll()
				linkList.Refresh()

				statusLabel.SetText(
					fmt.Sprintf("%d bookmarks found", len(links)),
				)
			})
		}()
	})

	clearSearchButton := widget.NewButton("Clear", func() {
		searchEntry.SetText("")

		serverURL := serverEntry.Text

		go func() {
			newLinks, err := getLinks(serverURL, apiToken, "")
			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText("Could not reload bookmarks")
				})
				return
			}

			fyne.Do(func() {
				links = newLinks
				linkList.Refresh()

				statusLabel.SetText(
					fmt.Sprintf("%d bookmarks", len(links)),
				)
			})
		}()
	})

	searchBar := container.NewBorder(
		nil,
		nil,
		nil,
		container.NewHBox(searchButton, clearSearchButton),
		searchEntry,
	)

	editButton := widget.NewButton("Edit Bookmark", func() {
		if selectedID < 0 {
			statusLabel.SetText("Select a bookmark first")
			return
		}

		if apiToken == "" {
			statusLabel.SetText("Connect first")
			return
		}

		rank, err := strconv.Atoi(rankEntry.Text)
		if err != nil {
			statusLabel.SetText("Rank must be a number")
			return
		}

		link := links[selectedID]

		serverURL := serverEntry.Text
		title := titleEntry.Text
		linkURL := urlEntry.Text

		statusLabel.SetText("Updating...")

		go func() {
			err := updateLink(
				serverURL,
				apiToken,
				link.ID,
				title,
				linkURL,
				rank,
			)

			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText(err.Error())
				})
				return
			}

			newLinks, err := getLinks(serverURL, apiToken, "")
			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText("Updated, but refresh failed")
				})
				return
			}

			fyne.Do(func() {
				links = newLinks
				selectedID = -1

				linkList.UnselectAll()
				linkList.Refresh()

				titleEntry.SetText("")
				urlEntry.SetText("")
				rankEntry.SetText("")

				statusLabel.SetText("Bookmark updated!")
			})
		}()
	})

	openButton := widget.NewButton("Open Bookmark", func() {
		if selectedID < 0 {
			statusLabel.SetText("Select a bookmark first")
			return
		}

		link := links[selectedID]

		linkURL, err := url.Parse(link.URL)
		if err != nil {
			statusLabel.SetText("Invalid URL")
			return
		}

		err = myApp.OpenURL(linkURL)
		if err != nil {
			statusLabel.SetText("Could not open URL")
			return
		}
	})

	deleteButton := widget.NewButton("Delete bookmark", func() {
		if selectedID < 0 {
			statusLabel.SetText("Select a bookmark first")
			return
		}

		link := links[selectedID]

		serverURL := serverEntry.Text

		go func() {
			err := deleteLink(serverURL, apiToken, link.ID)
			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText("Delete failed: " + err.Error())
				})
				return
			}

			newLinks, err := getLinks(serverURL, apiToken, "")
			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText("Deleted, but refresh failed")
				})
				return
			}

			fyne.Do(func() {
				links = newLinks
				selectedID = -1
				linkList.UnselectAll()
				linkList.Refresh()

				statusLabel.SetText("Bookmark deleted!")
			})
		}()
	})

	addButton := widget.NewButton("Add Bookmark", func() {
		title := titleEntry.Text
		linkURL := urlEntry.Text

		rank, err := strconv.Atoi(rankEntry.Text)
		if err != nil {
			statusLabel.SetText("Rank must be a number")
			return
		}

		if apiToken == "" {
			statusLabel.SetText("Connect first")
			return
		}

		serverURL := serverEntry.Text

		statusLabel.SetText("Adding bookmark...")

		go func() {
			err := addLink(
				serverURL,
				apiToken,
				title,
				linkURL,
				rank,
			)

			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText(err.Error())
				})
				return
			}

			newLinks, err := getLinks(serverURL, apiToken, "")
			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText("Added, but refresh failed")
				})
				return
			}

			fyne.Do(func() {
				links = newLinks
				linkList.Refresh()

				titleEntry.SetText("")
				urlEntry.SetText("")
				rankEntry.SetText("")

				statusLabel.SetText("Bookmark added!")
			})
		}()
	})

	connectButton := widget.NewButton("Connect", func() {
		serverURL := serverEntry.Text
		username := usernameEntry.Text
		password := passwordEntry.Text

		statusLabel.SetText("Connecting...")

		go func() {
			token, err := login(serverURL, username, password)
			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText("Login failed: " + err.Error())
				})
				return
			}

			newLinks, err := getLinks(serverURL, token, "")
			if err != nil {
				fyne.Do(func() {
					statusLabel.SetText("Could not get links: " + err.Error())
				})
				return
			}

			fyne.Do(func() {
				apiToken = token
				links = newLinks
				passwordEntry.SetText("")

				statusLabel.SetText(
					fmt.Sprintf("Connected! %d links", len(links)),
				)

				linkList.Refresh()
			})
		}()

	})

	loginArea := container.NewVBox(
		widget.NewLabel("Stelr Server URL"),
		serverEntry,

		widget.NewLabel("Username"),
		usernameEntry,
		widget.NewLabel("Password"),
		passwordEntry,

		connectButton,
		statusLabel,

		widget.NewSeparator(),
		widget.NewLabel("Add Bookmark"),
		widget.NewLabel("Title"),
		titleEntry,
		widget.NewLabel("URL"),
		urlEntry,
		widget.NewLabel("Rank"),
		rankEntry,

		addButton,
	)

	buttons := container.NewHBox(
		openButton,
		editButton,
		deleteButton,
	)

	bookmarkArea := container.NewBorder(
		searchBar,
		buttons,
		nil,
		nil,
		linkList,
	)

	content := container.NewBorder(
		loginArea,
		nil,
		nil,
		nil,
		bookmarkArea,
	)

	window.SetContent(content)
	window.Resize(fyne.NewSize(800, 600))

	window.ShowAndRun()
}
