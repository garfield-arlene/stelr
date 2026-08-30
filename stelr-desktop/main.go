package main

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"fyne.io/fyne/v2"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/layout"
	"fyne.io/fyne/v2/theme"
	"fyne.io/fyne/v2/widget"
)

//go:embed icon.png
var iconBytes []byte

type Link struct {
	ID      string `json:"id"`
	Title   string `json:"title"`
	URL     string `json:"url"`
	Rank    int    `json:"rank"`
	GroupID string `json:"group_id"`
}

var httpClient = &http.Client{
	Timeout: 10 * time.Second,
}

type largeTextTheme struct {
	fyne.Theme
}

func (t *largeTextTheme) Size(name fyne.ThemeSizeName) float32 {
	size := t.Theme.Size(name)

	if name == theme.SizeNameText {
		return size * 1.5
	}

	return size
}

func isInsecureRemote(serverURL string) bool {
	u, err := url.Parse(serverURL)
	if err != nil {
		return false
	}

	host := u.Hostname()

	return u.Scheme == "http" &&
		host != "localhost" &&
		host != "127.0.0.1"
}

func getLinks(serverURL, apiToken, search, rankOp, rankVal string) ([]Link, error) {

	baseURL := strings.TrimRight(serverURL, "/") + "/api/links"

	params := url.Values{}

	if search != "" {
		params.Set("q", search)
	}

	if rankOp != "" && rankVal != "" {
		params.Set("rank_op", rankOp)
		params.Set("rank_val", rankVal)
	}

	if len(params) > 0 {
		baseURL += "?" + params.Encode()
	}

	req, err := http.NewRequest("GET", baseURL, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", "Bearer "+apiToken)

	resp, err := httpClient.Do(req)
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

	req, err := http.NewRequest(
		"POST",
		url,
		bytes.NewBuffer(jsonData),
	)
	if err != nil {
		return "", err
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := httpClient.Do(req)
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

	resp, err := httpClient.Do(req)
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

	resp, err := httpClient.Do(req)
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

	resp, err := httpClient.Do(req)
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
	myApp.Settings().SetTheme(&largeTextTheme{
		Theme: theme.DefaultTheme(),
	})
	iconResource := fyne.NewStaticResource("icon.png", iconBytes)
	myApp.SetIcon(iconResource)

	window := myApp.NewWindow("Stelr Desktop")
	window.SetIcon(iconResource)

	serverEntry := widget.NewEntry()
	serverEntry.SetPlaceHolder("http://localhost:8082")

	usernameEntry := widget.NewEntry()

	passwordEntry := widget.NewPasswordEntry()

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

	rankOpSelect := widget.NewSelect(
		[]string{"<", "<=", "==", ">=", ">"},
		func(value string) {
		},
	)

	rankOpSelect.PlaceHolder = "Rank comparison"

	rankFilterEntry := widget.NewEntry()
	rankFilterEntry.SetPlaceHolder("Rank")

	rankBox := container.NewGridWrap(
		fyne.NewSize(70, rankFilterEntry.MinSize().Height),
		rankFilterEntry,
	)

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
		rankOp := rankOpSelect.Selected
		rankVal := rankFilterEntry.Text

		if rankVal != "" {
			_, err := strconv.Atoi(rankVal)
			if err != nil {
				statusLabel.SetText("Rank must be a number")
				return
			}
		}

		serverURL := serverEntry.Text

		go func() {
			newLinks, err := getLinks(serverURL, apiToken, search, rankOp, rankVal)
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
		rankFilterEntry.SetText("")
		rankOpSelect.ClearSelected()

		serverURL := serverEntry.Text

		go func() {
			newLinks, err := getLinks(serverURL, apiToken, "", "", "")
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

	searchBar := container.NewVBox(
		searchEntry,

		container.NewHBox(rankOpSelect, rankBox,
			layout.NewSpacer(), searchButton, clearSearchButton),
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

			newLinks, err := getLinks(serverURL, apiToken, "", "", "")
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

		dialog.ShowConfirm(
			"Delete Bookmark",
			"Are you sure you want to delete \""+link.Title+"\"?",
			func(ok bool) {
				if !ok {
					return
				}

				serverURL := serverEntry.Text

				go func() {
					err := deleteLink(serverURL, apiToken, link.ID)
					if err != nil {
						fyne.Do(func() {
							statusLabel.SetText("Delete failed: " + err.Error())
						})
						return
					}

					newLinks, err := getLinks(serverURL, apiToken, "", "", "")
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
			},
			window,
		)
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

			newLinks, err := getLinks(serverURL, apiToken, "", "", "")
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

	connectionArea := container.NewVBox()

	var showLoggedOut func()
	var showLoggedIn func(serverURL string)

	connectButton := widget.NewButton("Connect", func() {
		serverURL := serverEntry.Text
		username := usernameEntry.Text
		password := passwordEntry.Text

		connect := func() {
			statusLabel.SetText("Connecting...")

			go func() {
				token, err := login(serverURL, username, password)
				if err != nil {
					fyne.Do(func() {
						statusLabel.SetText("Login failed: " + err.Error())
					})
					return
				}

				newLinks, err := getLinks(serverURL, token, "", "", "")
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
					showLoggedIn(serverURL)
				})
			}()
		}

		if isInsecureRemote(serverURL) {
			dialog.ShowConfirm(
				"Insecure connection",
				"This server uses HTTP. Your username, password, and API token will not be encrypted. Continue?",
				func(ok bool) {
					if ok {
						connect()
					}
				},
				window,
			)

			return
		}

		connect()
	})

	showLoggedOut = func() {
		connectionArea.Objects = []fyne.CanvasObject{
			widget.NewLabel("Stelr Server URL"),
			serverEntry,

			widget.NewLabel("Username"),
			usernameEntry,
			widget.NewLabel("Password"),
			passwordEntry,

			connectButton,
			statusLabel,
		}
		connectionArea.Refresh()
	}

	showLoggedIn = func(serverURL string) {
		logoutButton := widget.NewButton("Log Out", func() {
			apiToken = ""
			links = nil
			selectedID = -1

			linkList.UnselectAll()
			linkList.Refresh()

			statusLabel.SetText("")
			showLoggedOut()
		})

		connectionArea.Objects = []fyne.CanvasObject{
			widget.NewLabel("Connected to " + serverURL),
			logoutButton,
			statusLabel,
		}
		connectionArea.Refresh()
	}

	showLoggedOut()

	sidebar := container.NewVBox(
		widget.NewLabelWithStyle("Connection", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
		connectionArea,

		widget.NewSeparator(),
		widget.NewLabelWithStyle("Add Bookmark", fyne.TextAlignLeading, fyne.TextStyle{Bold: true}),
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

	mainArea := container.NewBorder(
		searchBar,
		buttons,
		nil,
		nil,
		linkList,
	)

	split := container.NewHSplit(container.NewVScroll(sidebar), mainArea)
	split.SetOffset(0.28)

	window.SetContent(split)
	window.Resize(fyne.NewSize(900, 600))

	window.ShowAndRun()
}
